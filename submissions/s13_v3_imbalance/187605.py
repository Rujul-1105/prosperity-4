from datamodel import OrderDepth, TradingState, Order
from typing import List


class Trader:
    def __init__(self):
        self.ema = None
        self.prev_mid = None
        self.drift = 0.0

        self.alpha = 0.12
        self.drift_alpha = 0.10
        self.limit = 80

    def run(self, state: TradingState):
        result = {}
        product = "INTARIAN_PEPPER_ROOT"
        orders: List[Order] = []

        if product not in state.order_depths:
            return result, 0, ""

        order_depth = state.order_depths[product]

        if len(order_depth.buy_orders) == 0 or len(order_depth.sell_orders) == 0:
            return result, 0, ""

        best_bid = max(order_depth.buy_orders)
        best_ask = min(order_depth.sell_orders)
        mid = (best_bid + best_ask) / 2
        spread = max(1, best_ask - best_bid)

        # -------- EMA --------
        if self.ema is None:
            self.ema = mid
        else:
            self.ema = self.alpha * mid + (1 - self.alpha) * self.ema

        # -------- Drift --------
        if self.prev_mid is None:
            self.drift = 0
        else:
            raw_drift = mid - self.prev_mid
            self.drift = self.drift_alpha * raw_drift + (1 - self.drift_alpha) * self.drift

        self.prev_mid = mid

        trend = max(min(self.drift, 2), -2)   # clamp noise
        fair_value = self.ema + 6 * trend

        position = state.position.get(product, 0)

        signal = (fair_value - mid) / spread
        signal += -0.002 * position  # inventory bias

        # =====================
        # CORE STRATEGY
        # =====================

        bid_vol = sum(order_depth.buy_orders.values())
        ask_vol = -sum(order_depth.sell_orders.values())

        imbalance = 0
        if (bid_vol + ask_vol) > 0:
            imbalance = (bid_vol - ask_vol) / (bid_vol + ask_vol)

        signal += 0.1 * imbalance

        if signal > 0.25 and imbalance > 0:
            qty = min(10, self.limit - position)
            if qty > 0:
                orders.append(Order(product, best_ask, qty))

        elif signal < -0.25 and imbalance < 0:
            qty = min(10, position + self.limit)
            if qty > 0:
                orders.append(Order(product, best_bid, -qty))

        # =====================
        # FALLBACK (CRITICAL FIX)
        # =====================
        if len(orders) == 0:
            # Always place passive orders
            if position < self.limit:
                orders.append(Order(product, best_bid +5 , 2))
            if position > -self.limit:
                orders.append(Order(product, best_ask -2 , -2))

        # =====================
        # INVENTORY CONTROL
        # =====================
        if position > 50:
            orders.append(Order(product, best_ask, -8))

        if position < -8:
                repair_qty = min(5, -position)
                orders.append(Order(product, best_ask, repair_qty))

        result[product] = orders
        return result, 0, ""