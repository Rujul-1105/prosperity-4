from datamodel import OrderDepth, TradingState, Order
from typing import List
import numpy as np
from collections import deque

class Trader:

    def __init__(self):
        self.product = "HYDROGEL_PACK"

        self.limit = 180

        # === HISTORY ===
        self.mid_history = deque(maxlen=200)
        self.dev_history = deque(maxlen=500)
        self.price_change_history = deque(maxlen=50)

        # === MM ===
        self.mm_base_size = 20
        self.mm_reduced_size = 10

        # === Z PARAMETERS (SAFE) ===
        self.z_entry = 3.0
        self.z_add = 4.0
        self.z_exit_partial = 1.0
        self.z_exit_full = 0.0

    # ========================= HYDROGEL =========================
    def run_hydrogel(self, state: TradingState):
        product = self.product
        orders: List[Order] = []

        if product not in state.order_depths:
            return orders

        order_depth = state.order_depths[product]

        if not order_depth.buy_orders or not order_depth.sell_orders:
            return orders

        best_bid = max(order_depth.buy_orders)
        best_ask = min(order_depth.sell_orders)

        mid = (best_bid + best_ask) / 2
        position = state.position.get(product, 0)

        # HISTORY
        if len(self.mid_history) > 0:
            self.price_change_history.append(mid - self.mid_history[-1])

        self.mid_history.append(mid)

        if len(self.mid_history) < 100:
            return orders

        # FAIR VALUE
        ma50 = np.mean(list(self.mid_history)[-50:])
        ma200 = np.mean(self.mid_history)
        fair = 0.7 * ma50 + 0.3 * ma200

        # TREND
        short_ma = np.mean(list(self.mid_history)[-20:])
        long_ma = np.mean(list(self.mid_history)[-100:])
        trend = short_ma - long_ma
        slope = np.mean(np.diff(list(self.mid_history)[-20:]))

        strong_trend = abs(trend) > 5 or abs(slope) > 1.5

        # Z SCORE
        deviation = mid - fair
        self.dev_history.append(deviation)

        sigma = np.std(self.dev_history) if len(self.dev_history) > 50 else 10
        z = deviation / sigma if sigma > 0 else 0

        momentum = np.mean(self.price_change_history) if len(self.price_change_history) > 10 else 0

        long_cap = self.limit - position
        short_cap = self.limit + position

        # INVENTORY FLUSH
        if strong_trend:
            if trend < 0 and position > 0:
                orders.append(Order(product, best_bid, -min(position, 50)))
            elif trend > 0 and position < 0:
                orders.append(Order(product, best_ask, min(-position, 50)))

        # EXIT
        if position > 0:
            if z > -1:
                orders.append(Order(product, best_bid, -min(position // 2, 20)))
        elif position < 0:
            if z < 1:
                orders.append(Order(product, best_ask, min((-position) // 2, 20)))

        # ALLOW DIRECTIONAL
        allow_directional = True
        if strong_trend and abs(z) < 3.5:
            allow_directional = False

        # MEAN REVERSION
        if allow_directional and abs(position) < 160:

            if z > 3.0 and momentum < 0.5:
                size = min(25, short_cap)
                if size > 0:
                    orders.append(Order(product, best_bid, -size))

            elif z < -3.0 and momentum > -0.5:
                size = min(25, long_cap)
                if size > 0:
                    orders.append(Order(product, best_ask, size))

        # TREND FOLLOWING
        if strong_trend:

            if trend > 0 and z < -2:
                size = min(20, long_cap)
                if size > 0:
                    orders.append(Order(product, best_ask, size))

            elif trend < 0 and z > 2:
                size = min(20, short_cap)
                if size > 0:
                    orders.append(Order(product, best_bid, -size))

        # MM
        spread = int(max(4, min(8, 0.5 * sigma)))
        size = 20 if abs(position) <= 100 else 10

        bid_offset = -spread
        ask_offset = +spread

        if strong_trend:
            if trend > 0:
                ask_offset += 2
            else:
                bid_offset -= 2

        if long_cap > 0:
            orders.append(Order(product, int(fair + bid_offset), min(size, long_cap)))

        if short_cap > 0:
            orders.append(Order(product, int(fair + ask_offset), -min(size, short_cap)))

        return orders
    # ========================= RUN =========================
    def run(self, state: TradingState):
        result = {}

        orders = self.run_hydrogel(state)
        if orders:
            result[self.product] = orders

        return result, 0, ""