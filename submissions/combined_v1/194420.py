from datamodel import OrderDepth, TradingState, Order
from typing import List


class Trader:

    def __init__(self):
        # ===== CONFIG =====
        self.product = "INTARIAN_PEPPER_ROOT"

        self.position_limit = 80
        self.target_long = 60   # mild long bias

        self.ema = None
        self.prev_mid = None
        self.drift = 0.0

        self.alpha = 0.15          # EMA smoothing
        self.drift_alpha = 0.10    # drift smoothing

        self.trend_weight = 5.0    # how much trend shifts fair value
        self.buy_threshold = 0.15
        self.sell_threshold = 1.2

        self.osmium_ema = None
        self.osmium_alpha = 0.2

        self.osmium_std = 2.0   # from your data ~1.87
        self.osmium_limit = 80



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

        # Safe quoting
        if spread > 2:
            bid_price = best_bid + 1
            ask_price = best_ask - 1
        else:
            bid_price = best_bid
            ask_price = best_ask

        # Inventory-aware sizes
        buy_size = max(0, min(5, self.osmium_limit - position))
        sell_size = max(0, min(5, position + self.osmium_limit))

        if buy_size > 0:
            orders.append(Order(product, bid_price, buy_size))

        if sell_size > 0:
            orders.append(Order(product, ask_price, -sell_size))

        # Mean reversion
        if z > 2:
            qty = min(10, position + self.osmium_limit)
            if qty > 0:
                orders.append(Order(product, best_bid, -qty))

        elif z < -2:
            qty = min(10, self.osmium_limit - position)
            if qty > 0:
                orders.append(Order(product, best_ask, qty))

        # Extreme
        if z > 3:
            qty = min(15, position + self.osmium_limit)
            if qty > 0:
                orders.append(Order(product, best_bid, -qty))

        elif z < -3:
            qty = min(15, self.osmium_limit - position)
            if qty > 0:
                orders.append(Order(product, best_ask, qty))

        # Hard risk control
        if position > 60:
            orders.append(Order(product, best_ask, -min(10, position)))

        if position < -60:
            orders.append(Order(product, best_ask, min(10, -position)))

        return orders
        

    def run_pepper(self, state: TradingState):
        result = {}
        orders: List[Order] = []

        # ===== CHECK PRODUCT =====
        if self.product not in state.order_depths:
            return result, 0, ""

        order_depth = state.order_depths[self.product]

        if not order_depth.buy_orders or not order_depth.sell_orders:
            return result, 0, ""

        best_bid = max(order_depth.buy_orders)
        best_ask = min(order_depth.sell_orders)

        mid = (best_bid + best_ask) / 2
        spread = max(1, best_ask - best_bid)

        position = state.position.get(self.product, 0)

        # ===== EMA =====
        if self.ema is None:
            self.ema = mid
        else:
            self.ema = self.alpha * mid + (1 - self.alpha) * self.ema

        # ===== DRIFT =====
        if self.prev_mid is None:
            raw_drift = 0
        else:
            raw_drift = mid - self.prev_mid

        self.drift = self.drift_alpha * raw_drift + (1 - self.drift_alpha) * self.drift
        self.prev_mid = mid

        # Clamp noise
        trend = max(min(self.drift, 2), -2)

        # ===== FAIR VALUE =====
        fair_value = self.ema + self.trend_weight * trend

        # ===== SIGNAL =====
        signal = (fair_value - mid) / spread

        # inventory bias (push toward long)
        signal += 0.01 * (self.target_long - position)

        # ===== BUY LOGIC =====
        # if signal > self.buy_threshold:
        #     qty = min(10, self.position_limit - position)
        #     if qty > 0:
        #         # passive if possible, aggressive if strong
        #         if signal < 0.8:
        #             price = best_bid + 1
        #         else:
        #             price = best_ask
        #         orders.append(Order(self.product, price, qty))

        if signal > self.buy_threshold:
            qty = min(12, self.position_limit - position)

            if qty > 0:
                # more aggressive accumulation
                if position < self.target_long:
                    price = best_ask   # CROSS early → get position
                else:
                    price = best_bid + 1

                orders.append(Order(self.product, price, qty))
        # ===== SELL / TRIM LOGIC =====
        # elif signal < -self.sell_threshold:
        #     # DO NOT go meaningfully short
        #     max_sell = max(0, position)
        #     qty = min(10, max_sell)

        #     if qty > 0:
        #         if signal > -0.8:
        #             price = best_ask - 1
        #         else:
        #             price = best_bid
        #         orders.append(Order(self.product, price, -qty))

        # ===== SELL / TRIM LOGIC =====
        elif signal < -self.sell_threshold:
            # ONLY trim if VERY stretched AND very long
            if position > 50:
                qty = min(6, position - 50)
                if qty > 0:
                    orders.append(Order(self.product, best_bid, -qty))
        # ===== PASSIVE BASE QUOTES =====
        # else:
        #     # accumulate bias (prefer long)
        #     if position < self.target_long:
        #         orders.append(Order(self.product, best_bid + 1, 2))

        #     # light trimming only if above target
        #     if position > self.target_long + 10:
        #         orders.append(Order(self.product, best_ask - 1, -2))
        else:
            # keep building position slowly
            if position < self.target_long:
                orders.append(Order(self.product, best_bid + 1, 4))

            # very light trimming only if oversized
            if position > 70:
                orders.append(Order(self.product, best_ask - 1, -2))
        # ===== RISK CONTROL =====
        if position > 60:
            orders.append(Order(self.product, best_ask, -8))

        if position < -5:
            # quickly reduce shorts (we don't want them)
            orders.append(Order(self.product, best_ask, 6))

        result[self.product] = orders
        return orders


    def run(self, state: TradingState):
        result = {}

        # Pepper
        pepper_orders = self.run_pepper(state)
        if pepper_orders:
            result["INTARIAN_PEPPER_ROOT"] = pepper_orders

        # Osmium
        osmium_orders = self.run_osmium(state)
        if osmium_orders:
            result["ASH_COATED_OSMIUM"] = osmium_orders

        return result, 0, ""