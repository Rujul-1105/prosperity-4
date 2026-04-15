from datamodel import Order
import statistics

class Trader:

    def __init__(self):
        self.price_history = []

        # === PARAMETERS ===
        self.WINDOW = 50
        self.ENTRY_Z = 2
        self.EXIT_Z = 0.25
        self.POSITION_LIMIT = 80
        self.BASE_QTY = 4
        self.SPREAD_THRESHOLD = 18

    def run(self, state):

        result = {}

        for product in state.order_depths:
            result[product] = []

        product = "ASH_COATED_OSMIUM"

        if product not in state.order_depths:
            return result, 0, ""

        order_depth = state.order_depths[product]

        if not order_depth.buy_orders or not order_depth.sell_orders:
            return result, 0, ""

        best_bid = max(order_depth.buy_orders)
        best_ask = min(order_depth.sell_orders)

        mid_price = (best_bid + best_ask) / 2
        spread = best_ask - best_bid

        # === PRICE HISTORY ===
        self.price_history.append(mid_price)
        if len(self.price_history) > self.WINDOW:
            self.price_history.pop(0)

        if len(self.price_history) < 10:
            return result, 0, ""

        mean_price = statistics.mean(self.price_history)
        sigma = statistics.stdev(self.price_history)

        if sigma == 0:
            return result, 0, ""

        z = (mid_price - mean_price) / sigma
        position = state.position.get(product, 0)

        orders = []

        # === SPREAD FILTER ===
        if spread > self.SPREAD_THRESHOLD:
            return result, 0, ""

        # =========================
        # 🔴 1. AGGRESSIVE TRADING
        # =========================
        if z > self.ENTRY_Z:
            if position > -self.POSITION_LIMIT:
                volume = min(self.BASE_QTY, self.POSITION_LIMIT + position)
                orders.append(Order(product, best_bid, -volume))

        elif z < -self.ENTRY_Z:
            if position < self.POSITION_LIMIT:
                volume = min(self.BASE_QTY, self.POSITION_LIMIT - position)
                orders.append(Order(product, best_ask, volume))

        # =========================
        # 🟢 2. MARKET MAKING
        # =========================
        elif abs(z) < 1.0:
            # place passive quotes inside spread

            buy_price = best_bid + 3
            sell_price = best_ask - 3

            # inventory skew (important)
            skew = position * 0.2

            buy_price = int(buy_price - skew)
            sell_price = int(sell_price - skew)

            if position < self.POSITION_LIMIT:
                orders.append(Order(product, buy_price, self.BASE_QTY))

            if position > -self.POSITION_LIMIT:
                orders.append(Order(product, sell_price, -self.BASE_QTY))

        # =========================
        # 🟡 3. EXIT
        # =========================
        elif abs(z) < self.EXIT_Z:
            if position > 0:
                orders.append(Order(product, best_bid, -position))
            elif position < 0:
                orders.append(Order(product, best_ask, -position))

        result[product] = orders

        return result, 0, ""