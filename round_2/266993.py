from datamodel import OrderDepth, TradingState, Order
from typing import List


class Trader:

    def __init__(self):
        # ===== CONFIG =====
        self.product = "INTARIAN_PEPPER_ROOT"

        self.position_limit = 80
        self.target_long = 75   # increased from 60

        self.ema = None
        self.prev_mid = None
        self.drift = 0.0

        self.alpha = 0.15
        self.drift_alpha = 0.10

        self.trend_weight = 5.0
        self.buy_threshold = 0.15
        self.sell_threshold = 1.2

        # ===== OSMIUM =====
        self.osmium_ema = None
        self.osmium_alpha = 0.2

        self.osmium_std = 2.0
        self.osmium_limit = 80

        # tuning
        self.osmium_base_size = 6
        self.osmium_skew_factor = 0.12   # stronger skew
        self.osmium_noise_factor = 0.3
        self.osmium_spread_factor = 0.5

        self.osmium_anchor = 10000


    # ========================= OSMIUM =========================
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
            limit = self.osmium_limit

            # ===== EMA FAIR VALUE =====
            if self.osmium_ema is None:
                self.osmium_ema = mid
            else:
                self.osmium_ema = (
                    self.osmium_alpha * mid +
                    (1 - self.osmium_alpha) * self.osmium_ema
                )

            fair = self.osmium_ema
            z = (mid - fair) / self.osmium_std

            # =========================================================
            # 🔥 LAYER 1: TOUCH (PRIMARY FILL ENGINE)
            # =========================================================
            touch_bid = best_bid + 1
            touch_ask = best_ask - 1

            base_size = self.osmium_base_size + 4   # ~10

            # directional skew
            if z > 1:
                bid_size = 4
                ask_size = 14
            elif z < -1:
                bid_size = 14
                ask_size = 4
            else:
                bid_size = ask_size = base_size

            # inventory skew
            inv_skew = int(position * self.osmium_skew_factor)

            bid_size = max(1, bid_size - inv_skew)
            ask_size = max(1, ask_size + inv_skew)

            # clamp
            bid_size = min(bid_size, limit - position)
            ask_size = min(ask_size, position + limit)

            if bid_size > 0:
                orders.append(Order(product, int(touch_bid), int(bid_size)))

            if ask_size > 0:
                orders.append(Order(product, int(touch_ask), -int(ask_size)))

            # =========================================================
            # 🔥 LAYER 2: OUTER (SPREAD CAPTURE)
            # =========================================================
            outer_bid = best_bid - 2
            outer_ask = best_ask + 2

            outer_size = self.osmium_base_size

            if position < limit:
                orders.append(
                    Order(product, int(outer_bid),
                        int(min(outer_size, limit - position)))
                )

            if position > -limit:
                orders.append(
                    Order(product, int(outer_ask),
                        -int(min(outer_size, position + limit)))
                )

            # =========================================================
            # 🔥 INVENTORY RECYCLING (CRITICAL)
            # =========================================================
            if position > 60:
                orders.append(
                    Order(product, best_ask, -min(12, position))
                )

            elif position < -60:
                orders.append(
                    Order(product, best_bid, min(12, -position))
                )

            # =========================================================
            # 🔥 MISPRICING CAPTURE (ALPHA)
            # =========================================================
            if z > 2:
                qty = min(12, position + limit)
                if qty > 0:
                    orders.append(Order(product, best_bid, -qty))

            elif z < -2:
                qty = min(12, limit - position)
                if qty > 0:
                    orders.append(Order(product, best_ask, qty))

            return orders




    # ========================= PEPPER =========================
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

        # ===== STRONGER LONG BIAS =====
        signal += 0.02 * (self.target_long - position)

        # ===== BUY =====
        if signal > self.buy_threshold:
            qty = min(12, self.position_limit - position)

            if qty > 0:
                # SMART CROSSING
                if position < self.target_long:
                    if signal > 0.5:
                        price = best_ask   # strong → cross
                    else:
                        price = best_bid + 1   # otherwise passive
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

    # ========================= RUN =========================
    def run(self, state: TradingState):
        result = {}

        pepper_orders = self.run_pepper(state)
        if pepper_orders:
            result["INTARIAN_PEPPER_ROOT"] = pepper_orders

        osmium_orders = self.run_osmium(state)
        if osmium_orders:
            result["ASH_COATED_OSMIUM"] = osmium_orders

        return result, 0, ""