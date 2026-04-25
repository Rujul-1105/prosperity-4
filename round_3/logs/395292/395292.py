from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List, Dict
import numpy as np


class Trader:

    def __init__(self):
        self.mid_history = []
        self.norm_history: Dict[str, List[float]] = {}

        # Config
        self.lambda_ewma = 0.1
        self.z_window = 50

        self.z_threshold_liquid = 1.0
        self.z_threshold_illiquid = 1.5

        self.delta_threshold = 2

        # Limits
        self.underlying_limit = 200
        self.voucher_limit = 300

        self.liquid_strikes = ["VEV_5400", "VEV_5500", "VEV_6000", "VEV_6500"]
        self.illiquid_strikes = ["VEV_5200", "VEV_5300"]

    def get_mid(self, order_depth: OrderDepth):
        if len(order_depth.buy_orders) == 0 or len(order_depth.sell_orders) == 0:
            return None
        best_bid = max(order_depth.buy_orders.keys())
        best_ask = min(order_depth.sell_orders.keys())
        return (best_bid + best_ask) / 2

    def ewma(self, prev, new):
        return self.lambda_ewma * new + (1 - self.lambda_ewma) * prev

    def compute_zscore(self, product, price):
        if product not in self.norm_history:
            self.norm_history[product] = []

        hist = self.norm_history[product]
        hist.append(price)

        if len(hist) > self.z_window:
            hist.pop(0)

        if len(hist) < 10:
            return 0

        mean = np.mean(hist)
        std = np.std(hist) + 1e-6

        return (price - mean) / std

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}

        # ---------------------------
        # 1. UNDERLYING (VELVETFRUIT_EXTRACT)
        # ---------------------------
        if "VELVETFRUIT_EXTRACT" in state.order_depths:
            depth = state.order_depths["VELVETFRUIT_EXTRACT"]
            orders: List[Order] = []

            mid = self.get_mid(depth)

            if mid is not None:
                if len(self.mid_history) == 0:
                    S_hat = mid
                else:
                    S_hat = self.ewma(self.mid_history[-1], mid)

                self.mid_history.append(S_hat)

                spread = 2
                bid = int(S_hat - spread)
                ask = int(S_hat + spread)

                pos = state.position.get("VELVETFRUIT_EXTRACT", 0)

                # Inventory skew
                if pos > 0:
                    ask -= 1
                elif pos < 0:
                    bid += 1

                size = 10

                # Respect limits
                if pos < self.underlying_limit:
                    orders.append(Order("VELVETFRUIT_EXTRACT", bid, size))

                if pos > -self.underlying_limit:
                    orders.append(Order("VELVETFRUIT_EXTRACT", ask, -size))

            result["VELVETFRUIT_EXTRACT"] = orders

        # ---------------------------
        # 2. OPTIONS Z-SCORE TRADING
        # ---------------------------
        z_scores = {}

        for product, depth in state.order_depths.items():
            if "VEV_" not in product:
                continue

            mid = self.get_mid(depth)
            if mid is None:
                continue

            z = self.compute_zscore(product, mid)
            z_scores[product] = z

        for product, z in z_scores.items():
            depth = state.order_depths[product]
            orders: List[Order] = []

            pos = state.position.get(product, 0)
            mid = self.get_mid(depth)

            if mid is None:
                continue

            # Threshold selection
            if product in self.liquid_strikes:
                threshold = self.z_threshold_liquid
            else:
                threshold = self.z_threshold_illiquid

            size = int(10 * abs(z))
            size = min(size, self.voucher_limit - abs(pos))

            if size <= 0:
                continue

            # SELL overpriced
            if z > threshold and len(depth.buy_orders) > 0:
                best_bid = max(depth.buy_orders.keys())
                orders.append(Order(product, best_bid, -size))

            # BUY underpriced
            elif z < -threshold and len(depth.sell_orders) > 0:
                best_ask = min(depth.sell_orders.keys())
                orders.append(Order(product, best_ask, size))

            if len(orders) > 0:
                result[product] = orders

        # ---------------------------
        # 3. DELTA HEDGE
        # ---------------------------
        total_delta = 0

        for product, pos in state.position.items():
            if "VEV_" in product:
                total_delta += 0.15 * pos
            elif product == "VELVETFRUIT_EXTRACT":
                total_delta += pos

        if "VELVETFRUIT_EXTRACT" in state.order_depths:
            depth = state.order_depths["VELVETFRUIT_EXTRACT"]
            hedge_orders: List[Order] = []

            pos = state.position.get("VELVETFRUIT_EXTRACT", 0)

            if total_delta > self.delta_threshold and len(depth.buy_orders) > 0:
                best_bid = max(depth.buy_orders.keys())
                hedge_orders.append(Order("VELVETFRUIT_EXTRACT", best_bid, -10))

            elif total_delta < -self.delta_threshold and len(depth.sell_orders) > 0:
                best_ask = min(depth.sell_orders.keys())
                hedge_orders.append(Order("VELVETFRUIT_EXTRACT", best_ask, 10))

            if len(hedge_orders) > 0:
                if "VELVETFRUIT_EXTRACT" in result:
                    result["VELVETFRUIT_EXTRACT"] += hedge_orders
                else:
                    result["VELVETFRUIT_EXTRACT"] = hedge_orders

        # ---------------------------
        # FINAL RETURN
        # ---------------------------
        traderData = ""
        conversions = 0

        return result, conversions, traderData