from datamodel import OrderDepth, TradingState, Order
from typing import List


class Trader:

    def __init__(self):
        self.position_limit = 80
        self.soft_limit = 40
        self.hard_limit = 64

        self.k_pos = 0.02
        self.base_spread = 1

        self.prices = []

    def run(self, state: TradingState):

        result = {}
        conversions = 0
        traderData = ""

        for product in state.order_depths:

            # ✅ FIXED PRODUCT NAME
            if product != "ASH_COATED_OSMIUM":
                result[product] = []
                continue

            order_depth = state.order_depths[product]
            orders: List[Order] = []

            if not order_depth.buy_orders or not order_depth.sell_orders:
                result[product] = orders
                continue

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())

            bid_vol = order_depth.buy_orders[best_bid]
            ask_vol = -order_depth.sell_orders[best_ask]

            mid = (best_bid + best_ask) // 2

            self.prices.append(mid)

            if len(self.prices) < 5:
                fair = mid
                std = 1
            else:
                window = self.prices[-20:]
                fair = sum(window) / len(window)
                var = sum((p - fair) ** 2 for p in window) / len(window)
                std = var ** 0.5 if var > 0 else 1

            upper = fair + 2 * std
            lower = fair - 2 * std

            denom = bid_vol + ask_vol
            if denom == 0:
                mp = mid
                imb = 0
            else:
                mp = (best_bid * ask_vol + best_ask * bid_vol) / denom
                imb = (bid_vol - ask_vol) / denom

            position = state.position.get(product, 0)
            abs_pos = abs(position)

            spread = self.base_spread
            threshold = 0.2 * std

            # =========================
            # NORMAL MODE
            # =========================
            if abs_pos <= self.soft_limit:

                skew = self.k_pos * position

                bid_price = int(fair - spread - skew)
                ask_price = int(fair + spread - skew)

                orders.append(Order(product, bid_price, 10))
                orders.append(Order(product, ask_price, -10))

                if mid <= lower - threshold and mp > mid and imb > 0.2:
                    size = min(20, self.position_limit - position)
                    if size > 0:
                        orders.append(Order(product, best_ask, size))

                if mid >= upper + threshold and mp < mid and imb < -0.2:
                    size = min(20, self.position_limit + position)
                    if size > 0:
                        orders.append(Order(product, best_bid, -size))

            # =========================
            # SOFT LIMIT
            # =========================
            elif abs_pos <= self.hard_limit:

                skew = 2 * self.k_pos * position

                if position > 0:
                    ask_price = int(fair + spread - skew)
                    orders.append(Order(product, ask_price, -10))
                else:
                    bid_price = int(fair - spread - skew)
                    orders.append(Order(product, bid_price, 10))

            # =========================
            # HARD LIMIT
            # =========================
            else:

                skew = 3 * self.k_pos * position

                if position > 0:
                    size = min(20, position)
                    orders.append(Order(product, best_bid, -size))
                else:
                    size = min(20, -position)
                    orders.append(Order(product, best_ask, size))

                if position > 0:
                    ask_price = int(fair - skew)
                    orders.append(Order(product, ask_price, -10))
                else:
                    bid_price = int(fair - skew)
                    orders.append(Order(product, bid_price, 10))

            # ✅ CRITICAL: ensure at least some activity
            if len(orders) == 0:
                orders.append(Order(product, best_bid, 1))
                orders.append(Order(product, best_ask, -1))

            result[product] = orders

        return result, conversions, traderData