from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict


class Trader:

    def __init__(self):
        # LIMITS
        self.position_limit = 80
        self.soft_limit = 25
        self.hard_limit = 50

        # MODEL
        self.base_spread = 2
        self.sigma = 2.3

        # EMA
        self.ema = None
        self.ema_fast = None
        self.ema_slow = None

        # ORDER SIZE
        self.base_size = 10

        # Z HISTORY
        self.z_history = []

    # ---------------- HELPERS ----------------

    def update_ema(self, price, alpha):
        if self.ema is None:
            self.ema = price
        else:
            self.ema = alpha * price + (1 - alpha) * self.ema
        return self.ema

    def update_trend_ema(self, price):
        if self.ema_fast is None:
            self.ema_fast = price
            self.ema_slow = price
        else:
            self.ema_fast = 0.2 * price + 0.8 * self.ema_fast
            self.ema_slow = 0.05 * price + 0.95 * self.ema_slow

        if self.ema_fast > self.ema_slow:
            return "UP"
        elif self.ema_fast < self.ema_slow:
            return "DOWN"
        return "FLAT"

    def detect_regime(self, z):
        # maintain history
        self.z_history.append(z)
        if len(self.z_history) > 20:
            self.z_history.pop(0)

        sign_changes = sum(
            1 for i in range(1, len(self.z_history))
            if self.z_history[i] * self.z_history[i - 1] < 0
        )

        trend_strength = abs(self.ema_fast - self.ema_slow)

        if trend_strength > 1.5 and sign_changes < 6:
            return "TREND"
        return "MEAN"

    def adaptive_alpha(self, z):
        return 0.05 if abs(z) < 2 else 0.1

    def compute_z(self, price, fair):
        return (price - fair) / self.sigma

    def classify_inventory(self, pos):
        if abs(pos) < self.soft_limit:
            return "SAFE"
        elif abs(pos) < self.hard_limit:
            return "WARNING"
        else:
            return "DANGER"

    def skew(self, position):
        return -0.15 * position

    def get_spread(self, regime):
        if regime == "MEAN":
            return self.base_spread
        return self.base_spread + 1

    def get_size(self, regime, inv_zone):
        size = self.base_size

        if regime == "TREND":
            size = int(size * 1.5)

        if inv_zone == "WARNING":
            size = int(size * 0.7)
        elif inv_zone == "DANGER":
            size = int(size * 0.4)

        return max(1, size)

    # ---------------- MAIN ----------------

    def run(self, state: TradingState):

        product = "ASH_COATED_OSMIUM"
        result: Dict[str, List[Order]] = {}

        if product not in state.order_depths:
            return result, 0, ""

        order_depth: OrderDepth = state.order_depths[product]
        orders: List[Order] = []

        if not order_depth.buy_orders or not order_depth.sell_orders:
            result[product] = orders
            return result, 0, ""

        best_bid = max(order_depth.buy_orders.keys())
        best_ask = min(order_depth.sell_orders.keys())

        mid = (best_bid + best_ask) / 2
        position = state.position.get(product, 0)

        # -------- EMA --------
        z_temp = 0 if self.ema is None else self.compute_z(mid, self.ema)
        alpha = self.adaptive_alpha(z_temp)
        fair = self.update_ema(mid, alpha)

        # -------- TREND --------
        trend_dir = self.update_trend_ema(mid)

        # -------- SIGNAL --------
        z = self.compute_z(mid, fair)
        regime = self.detect_regime(z)
        inv_zone = self.classify_inventory(position)

        spread = self.get_spread(regime)
        skew = self.skew(position)
        size = self.get_size(regime, inv_zone)

        # -------- HARD RISK --------
        if inv_zone == "DANGER":
            reduce_qty = min(size * 2, abs(position))
            if position > 0:
                orders.append(Order(product, best_bid, -reduce_qty))
            elif position < 0:
                orders.append(Order(product, best_ask, reduce_qty))
            result[product] = orders
            return result, 0, ""

        # -------- MARKET MAKING --------
        bid_price = int(fair - spread + skew)
        ask_price = int(fair + spread + skew)

        buy_qty = max(0, min(size, self.position_limit - position))
        sell_qty = max(0, min(size, self.position_limit + position))

        if regime == "MEAN":
            # normal MM
            if buy_qty > 0:
                orders.append(Order(product, bid_price, buy_qty))
            if sell_qty > 0:
                orders.append(Order(product, ask_price, -sell_qty))

        elif regime == "TREND":
            # bias with trend
            if trend_dir == "UP":
                if buy_qty > 0:
                    orders.append(Order(product, bid_price + 1, buy_qty))
            elif trend_dir == "DOWN":
                if sell_qty > 0:
                    orders.append(Order(product, ask_price - 1, -sell_qty))

        # -------- AGGRESSION --------

        if regime == "MEAN":
            # mean reversion trades
            if z > 2:
                orders.append(Order(product, best_bid, -size))
            elif z < -2:
                orders.append(Order(product, best_ask, size))

        elif regime == "TREND":
            # follow trend instead of fading
            if trend_dir == "UP" and z < -1:
                orders.append(Order(product, best_ask, size))
            elif trend_dir == "DOWN" and z > 1:
                orders.append(Order(product, best_bid, -size))

        # -------- EXIT --------
        if position > 0:
            if z >= 0:
                orders.append(Order(product, best_bid, -position))
            elif z >= -1:
                orders.append(Order(product, best_bid, -position // 2))

        elif position < 0:
            if z <= 0:
                orders.append(Order(product, best_ask, -position))
            elif z <= 1:
                orders.append(Order(product, best_ask, (-position) // 2))

        result[product] = orders
        return result, 0, ""