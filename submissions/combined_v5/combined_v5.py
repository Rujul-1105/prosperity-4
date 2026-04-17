from datamodel import OrderDepth, TradingState, Order
from typing import List


class Trader:

    def __init__(self):
        # ===== PEPPER (V3) =====
        self.product = "INTARIAN_PEPPER_ROOT"

        self.position_limit = 80
        self.target_long = 75

        self.ema = None
        self.prev_mid = None
        self.drift = 0.0

        self.alpha = 0.15
        self.drift_alpha = 0.10

        self.trend_weight = 5.0
        self.buy_threshold = 0.15
        self.sell_threshold = 1.2

        # ===== OSMIUM (V1) =====
        self.osmium_ema = None
        self.osmium_alpha = 0.2

        self.osmium_std = 2.0
        self.osmium_limit = 80


    # ================= OSMIUM V1 =================
    def run_osmium(self, state):
        product = "ASH_COATED_OSMIUM"
        orders = []

        if product not in state.order_depths:
            return orders

        order_depth = state.order_depths[product]
        if not order_depth.buy_orders or not order_depth.sell_orders:
            return orders

        best_bid = max(order_depth.buy_orders)
        best_ask = min(order_depth.sell_orders)

        mid = (best_bid + best_ask) / 2
        spread = best_ask - best_bid
        position = state.position.get(product, 0)

        # EMA
        if self.osmium_ema is None:
            self.osmium_ema = mid
        else:
            self.osmium_ema = self.osmium_alpha * mid + (1 - self.osmium_alpha) * self.osmium_ema

        fair_value = self.osmium_ema
        z = (mid - fair_value) / self.osmium_std

        bid_price = best_bid + 1 if spread > 2 else best_bid
        ask_price = best_ask - 1 if spread > 2 else best_ask

        buy_size = max(0, min(5, self.osmium_limit - position))
        sell_size = max(0, min(5, position + self.osmium_limit))

        if buy_size:
            orders.append(Order(product, bid_price, buy_size))
        if sell_size:
            orders.append(Order(product, ask_price, -sell_size))

        if z > 2:
            orders.append(Order(product, best_bid, -min(10, position + self.osmium_limit)))
        elif z < -2:
            orders.append(Order(product, best_ask, min(10, self.osmium_limit - position)))

        if z > 3:
            orders.append(Order(product, best_bid, -min(15, position + self.osmium_limit)))
        elif z < -3:
            orders.append(Order(product, best_ask, min(15, self.osmium_limit - position)))

        if position > 60:
            orders.append(Order(product, best_ask, -10))
        if position < -60:
            orders.append(Order(product, best_ask, 10))

        return orders


    # ================= PEPPER V3 =================
    def run_pepper(self, state: TradingState):
        orders: List[Order] = []

        if self.product not in state.order_depths:
            return orders

        order_depth = state.order_depths[self.product]
        if not order_depth.buy_orders or not order_depth.sell_orders:
            return orders

        best_bid = max(order_depth.buy_orders)
        best_ask = min(order_depth.sell_orders)

        mid = (best_bid + best_ask) / 2
        spread = max(1, best_ask - best_bid)
        position = state.position.get(self.product, 0)

        # EMA
        if self.ema is None:
            self.ema = mid
        else:
            self.ema = self.alpha * mid + (1 - self.alpha) * self.ema

        # Drift
        raw_drift = 0 if self.prev_mid is None else mid - self.prev_mid
        self.drift = self.drift_alpha * raw_drift + (1 - self.drift_alpha) * self.drift
        self.prev_mid = mid

        trend = max(min(self.drift, 2), -2)
        fair_value = self.ema + self.trend_weight * trend

        signal = (fair_value - mid) / spread
        signal += 0.02 * (self.target_long - position)

        # BUY
        if signal > self.buy_threshold:
            qty = min(12, self.position_limit - position)

            if qty > 0:
                if position < self.target_long:
                    price = best_ask if signal > 0.5 else best_bid + 1
                else:
                    price = best_bid + 1

                orders.append(Order(self.product, price, qty))

        # SELL
        elif signal < -self.sell_threshold:
            if position > 50:
                qty = min(6, position - 50)
                if qty > 0:
                    orders.append(Order(self.product, best_bid, -qty))

        # PASSIVE
        else:
            if position < self.target_long:
                orders.append(Order(self.product, best_bid + 1, 4))

            if position > 70:
                orders.append(Order(self.product, best_ask - 1, -2))

        # RISK
        if position > 60:
            orders.append(Order(self.product, best_ask, -8))

        if position < -5:
            orders.append(Order(self.product, best_ask, 6))

        return orders


    def run(self, state: TradingState):
        result = {}

        result["INTARIAN_PEPPER_ROOT"] = self.run_pepper(state)
        result["ASH_COATED_OSMIUM"] = self.run_osmium(state)

        return result, 0, ""