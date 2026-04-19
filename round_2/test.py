from datamodel import OrderDepth, TradingState, Order
from typing import List


class Trader:

    def __init__(self):
    # ===== OSMIUM =====
        self.osmium_ema = None
        self.osmium_alpha = 0.2

        # dynamic variance for z-score
        self.osmium_var = 1.0

        # position control
        self.osmium_limit = 80

        # tuning params
        self.osmium_skew_factor = 0.1
        self.osmium_order_size = 5

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

        # =========================
        # EMA + VARIANCE
        # =========================
        if self.osmium_ema is None:
            self.osmium_ema = mid
            self.osmium_var = 1.0
        else:
            self.osmium_ema = 0.2 * mid + 0.8 * self.osmium_ema

            dev = mid - self.osmium_ema
            self.osmium_var = 0.9 * self.osmium_var + 0.1 * (dev ** 2)

        std = max(1e-6, self.osmium_var ** 0.5)

        z = (mid - self.osmium_ema) / std

        ENTRY_THRESHOLD = 1.8
        EXIT_THRESHOLD = 0.3
        LIMIT = self.osmium_limit

        # =========================
        # INVENTORY SKEW
        # =========================
        skew = position * 0.1
        fair = self.osmium_ema - skew

        # =========================
        # SAFE WIDE QUOTES
        # =========================
        base_spread = max(6, spread)

        bid_price = int(fair - base_spread)
        ask_price = int(fair + base_spread)

        # =========================
        # PASSIVE ONLY WHEN NO SIGNAL
        # =========================
        if abs(z) < ENTRY_THRESHOLD:
            buy_size = max(0, min(2, LIMIT - position))
            sell_size = max(0, min(2, position + LIMIT))

            if buy_size > 0:
                orders.append(Order(product, bid_price, buy_size))

            if sell_size > 0:
                orders.append(Order(product, ask_price, -sell_size))

        # =========================
        # AGGRESSIVE MEAN REVERSION
        # =========================
        if z > ENTRY_THRESHOLD:
            # SELL
            qty = min(10, position + LIMIT)
            if qty > 0:
                orders.append(Order(product, best_bid - 1, -qty))

        elif z < -ENTRY_THRESHOLD:
            # BUY
            qty = min(10, LIMIT - position)
            if qty > 0:
                orders.append(Order(product, best_ask + 1, qty))

        # =========================
        # EXIT LOGIC
        # =========================
        if abs(z) < EXIT_THRESHOLD:
            if position > 0:
                orders.append(Order(product, best_bid - 1, -min(10, position)))
            elif position < 0:
                orders.append(Order(product, best_ask + 1, min(10, -position)))

        # =========================
        # HARD RISK CONTROL
        # =========================
        if position > LIMIT * 0.8:
            orders.append(Order(product, best_bid - 1, -min(10, position)))

        if position < -LIMIT * 0.8:
            orders.append(Order(product, best_ask + 1, min(10, -position)))

        return orders
    # ========================= PEPPER =========================
    def run_pepper(self, state: TradingState):
        return []  # <-- DISABLED FOR NOW

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