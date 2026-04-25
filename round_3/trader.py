from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
from collections import deque
import numpy as np


class Trader:
    def __init__(self):
        self.product = "HYDROGEL_PACK"
        self.limit = 180

        # --- history ---
        self.mid_history = deque(maxlen=400)
        self.imbalance_history = deque(maxlen=500)
        self.edge_history = deque(maxlen=500)

        # --- state ---
        self.ema_fast = None
        self.ema_slow = None

        # --- parameters ---
        self.anchor_price = 10000.0

        self.ema_fast_alpha = 0.24
        self.ema_slow_alpha = 0.06

        # thresholds
        self.entry_z = 2.2
        self.extreme_z = 3.0
        self.exit_z = 0.1

        self.directional_size = 10
        self.directional_size_extreme = 18

        self.inventory_soft = 80
        self.inventory_hard = 140

    # -------- helpers --------
    @staticmethod
    def _best_prices(order_depth: OrderDepth):
        return max(order_depth.buy_orders), min(order_depth.sell_orders)

    @staticmethod
    def _book_imbalance(order_depth: OrderDepth):
        bid = sum(order_depth.buy_orders.values())
        ask = sum(abs(v) for v in order_depth.sell_orders.values())
        if bid + ask == 0:
            return 0
        return (bid - ask) / (bid + ask)

    @staticmethod
    def _microprice(bid, ask, bid_vol, ask_vol):
        if bid_vol + ask_vol == 0:
            return (bid + ask) / 2
        return (bid * ask_vol + ask * bid_vol) / (bid_vol + ask_vol)

    def _zscore(self, val, hist):
        if len(hist) < 20:
            return 0
        arr = np.array(hist)
        return (val - np.mean(arr)) / (np.std(arr) + 1e-6)

    def _update_ema(self, mid):
        if self.ema_fast is None:
            self.ema_fast = mid
            self.ema_slow = mid
        else:
            self.ema_fast = self.ema_fast_alpha * mid + (1 - self.ema_fast_alpha) * self.ema_fast
            self.ema_slow = self.ema_slow_alpha * mid + (1 - self.ema_slow_alpha) * self.ema_slow

    def _fair(self, mid):
        return (
            0.5 * self.anchor_price +
            0.25 * self.ema_fast +
            0.25 * self.ema_slow
        )

    def _trend(self):
        if len(self.mid_history) < 80:
            return "NEUTRAL"

        short = np.mean(list(self.mid_history)[-20:])
        long = np.mean(list(self.mid_history)[-80:])

        if short - long > 3:
            return "UP"
        if short - long < -3:
            return "DOWN"
        return "NEUTRAL"

    # -------- main --------
    def run_hydrogel(self, state: TradingState):

        orders = []

        if self.product not in state.order_depths:
            return orders

        od = state.order_depths[self.product]

        if not od.buy_orders or not od.sell_orders:
            return orders

        bid, ask = self._best_prices(od)
        mid = (bid + ask) / 2
        position = state.position.get(self.product, 0)

        bid_vol = abs(od.buy_orders[bid])
        ask_vol = abs(od.sell_orders[ask])

        imbalance = self._book_imbalance(od)
        micro = self._microprice(bid, ask, bid_vol, ask_vol)

        # --- update ---
        self.mid_history.append(mid)
        self._update_ema(mid)

        fair = self._fair(mid)

        # --- EDGE (microprice based) ---
        edge = micro - fair
        self.edge_history.append(edge)

        z = self._zscore(edge, self.edge_history)
        flow_z = self._zscore(imbalance, self.imbalance_history)
        self.imbalance_history.append(imbalance)

        # --- SIMPLIFIED TIMING (very light filter) ---
        z_prev = z
        if len(self.edge_history) > 2:
            prev_edge = self.edge_history[-2]
            z_prev = self._zscore(prev_edge, self.edge_history)

        trend = self._trend()

        long_cap = self.limit - position
        short_cap = self.limit + position

        # --- HARD RISK ---
        if abs(position) > self.inventory_hard:
            if position > 0:
                orders.append(Order(self.product, bid, -position))
            else:
                orders.append(Order(self.product, ask, -position))
            return orders

        # --- FLOW FILTER ---
        if abs(flow_z) > 1.5:
            return orders

        # --- TREND LOGIC ---
        if trend == "DOWN":

            if position > 0:
                orders.append(Order(self.product, bid, -min(position, 20)))

            # 🔥 TIMING FILTER APPLIED
            if z > self.entry_z:
                size = min(self.directional_size, short_cap)
                orders.append(Order(self.product, bid, -size))

            return orders

        if trend == "UP":

            if position < 0:
                orders.append(Order(self.product, ask, min(-position, 20)))

            # 🔥 TIMING FILTER APPLIED
            if z < -self.entry_z:
                size = min(self.directional_size, long_cap)
                orders.append(Order(self.product, ask, size))

            return orders

        # --- NEUTRAL MEAN REVERSION ---
        if z < -self.entry_z:
            size = min(self.directional_size, long_cap)
            orders.append(Order(self.product, ask, size))

        elif z > self.entry_z:
            size = min(self.directional_size, short_cap)
            orders.append(Order(self.product, bid, -size))

        # --- FAST EXIT ---
        if position > 0 and z > -self.exit_z:
            orders.append(Order(self.product, bid, -min(position, 15)))

        if position < 0 and z < self.exit_z:
            orders.append(Order(self.product, ask, min(-position, 15)))

        return orders

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}

        orders = self.run_hydrogel(state)
        if orders:
            result[self.product] = orders

        return result, 0, ""
