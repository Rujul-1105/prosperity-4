from datamodel import OrderDepth, TradingState, Order
from typing import List


class Trader:

    def __init__(self):
        # ===================== PEPPER =====================
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

        # ===================== OSMIUM =====================
        self.osmium_ema = None
        self.osmium_alpha = 0.35

        self.osmium_std = 1.8   # tighter → faster reaction
        self.osmium_limit = 80

        self.osmium_anchor = 10000  # TRUE FAIR VALUE

    # ===================== OSMIUM =====================
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
        spread = max(1, best_ask - best_bid)

        position = state.position.get(product, 0)

        # ===== EMA =====
        if self.osmium_ema is None:
            self.osmium_ema = mid
        else:
            self.osmium_ema = 0.35 * mid + 0.65 * self.osmium_ema

        # ===== FAIR VALUE =====
        fair_value = 0.85 * self.osmium_ema + 0.15 * self.osmium_anchor

        # ===== MICROPRICE (SAFE) =====
        best_bid_vol = order_depth.buy_orders.get(best_bid, 1)
        best_ask_vol = abs(order_depth.sell_orders.get(best_ask, -1))

        denom = best_bid_vol + best_ask_vol
        if denom > 0:
            microprice = (best_ask * best_bid_vol + best_bid * best_ask_vol) / denom
            fair_value += 0.4 * (microprice - mid)

        # ===== Z-SCORE =====
        z = (mid - fair_value) / 2.0

        # ===== SIZE =====
        inventory_penalty = int(abs(position) / 20)
        base_size = max(2, 3 + int(abs(z)) - inventory_penalty)
        # base_size = 3 + int(abs(z))

        # ===== INVENTORY CONTROL =====
        skew = int(position / 25)

        edge = max(1, spread // 4)

        bid_price = int(best_bid + edge - skew)
        ask_price = int(best_ask - edge - skew)

        # ===== SELECTIVE MARKET MAKING =====
        if z > 1.2:
            orders.append(Order(product, ask_price, -base_size))

        elif z < -1.2:
            orders.append(Order(product, bid_price, base_size))

        else:
            orders.append(Order(product, bid_price, base_size))
            orders.append(Order(product, ask_price, -base_size))

        # ===== MEAN REVERSION =====
        if z > 2:
            qty = min(10, position + 80)
            if qty > 0:
                orders.append(Order(product, best_bid, -qty))

        elif z < -2:
            qty = min(10, 80 - position)
            if qty > 0:
                orders.append(Order(product, best_ask, qty))

        # ===== EXTREME =====
        if z > 3:
            qty = min(20, position + 80)
            orders.append(Order(product, best_bid, -qty))

        elif z < -3:
            qty = min(20, 80 - position)
            orders.append(Order(product, best_ask, qty))

        # ===== RISK =====
        if position > 60:
            orders.append(Order(product, best_ask, -12))

        if position < -60:
            orders.append(Order(product, best_ask, 12))

        # ===== INVENTORY MEAN REVERSION =====
        if position > 30:
            orders.append(Order(product, best_ask, -min(15, position - 30)))

        elif position < -30:
            orders.append(Order(product, best_ask, min(15, -30 - position)))

        return orders
    # ===================== PEPPER =====================
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
        if self.prev_mid is None:
            raw_drift = 0
        else:
            raw_drift = mid - self.prev_mid

        self.drift = self.drift_alpha * raw_drift + (1 - self.drift_alpha) * self.drift
        self.prev_mid = mid

        trend = max(min(self.drift, 2), -2)

        fair_value = self.ema + self.trend_weight * trend

        signal = (fair_value - mid) / spread

        # stronger long bias
        signal += 0.02 * (self.target_long - position)

        # ===== BUY =====
        if signal > self.buy_threshold:
            qty = min(12, self.position_limit - position)

            if qty > 0:
                if position < self.target_long:
                    if signal > 0.5:
                        price = best_ask
                    else:
                        price = best_bid + 1
                else:
                    price = best_bid + 1

                orders.append(Order(self.product, price, qty))

        # ===== SELL / TRIM =====
        elif signal < -self.sell_threshold:
            if position > 50:
                qty = min(6, position - 50)
                if qty > 0:
                    orders.append(Order(self.product, best_bid, -qty))

        # ===== PASSIVE =====
        else:
            if position < self.target_long:
                orders.append(Order(self.product, best_bid + 1, 4))

            if position > 70:
                orders.append(Order(self.product, best_ask - 1, -2))

        # ===== RISK =====
        if position > 60:
            orders.append(Order(self.product, best_ask, -8))

        if position < -5:
            orders.append(Order(self.product, best_ask, 6))

        return orders

    # ===================== RUN =====================
    def run(self, state: TradingState):
        result = {}

        pepper_orders = self.run_pepper(state)
        if pepper_orders:
            result["INTARIAN_PEPPER_ROOT"] = pepper_orders

        osmium_orders = self.run_osmium(state)
        if osmium_orders:
            result["ASH_COATED_OSMIUM"] = osmium_orders

        return result, 0, ""