from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict


class Trader:
    def __init__(self):
        self.ema_price = {}
        self.prev_mid = {}
        self.drift_estimate = {}
        self.alpha = 0.12
        self.drift_alpha = 0.10

        self.POSITION_LIMIT = {
            "INTARIAN_PEPPER_ROOT": 80
        }

    def compute_mid_price(self, order_depth: OrderDepth):
        if not order_depth.buy_orders or not order_depth.sell_orders:
            return None

        best_bid = max(order_depth.buy_orders.keys())
        best_ask = min(order_depth.sell_orders.keys())
        return (best_bid + best_ask) / 2

    def update_ema(self, product: str, price: float) -> float:
        if product not in self.ema_price:
            self.ema_price[product] = price
        else:
            self.ema_price[product] = self.alpha * price + (1 - self.alpha) * self.ema_price[product]
        return self.ema_price[product]

    def update_drift(self, product: str, mid: float) -> float:
        if product not in self.prev_mid:
            self.prev_mid[product] = mid
            self.drift_estimate[product] = 0.0
            return 0.0

        raw_drift = mid - self.prev_mid[product]
        self.prev_mid[product] = mid

        if product not in self.drift_estimate:
            self.drift_estimate[product] = raw_drift
        else:
            self.drift_estimate[product] = (
                self.drift_alpha * raw_drift + (1 - self.drift_alpha) * self.drift_estimate[product]
            )
        return self.drift_estimate[product]

    def run(self, state: TradingState) -> Dict[str, List[Order]]:
        result = {}

        product = "INTARIAN_PEPPER_ROOT"
        orders: List[Order] = []

        if product not in state.order_depths:
            result[product] = orders
            return result

        order_depth = state.order_depths[product]
        mid = self.compute_mid_price(order_depth)

        if mid is None:
            result[product] = orders
            return result

        best_bid = max(order_depth.buy_orders.keys())
        best_ask = min(order_depth.sell_orders.keys())
        spread = max(1, best_ask - best_bid)

        ema = self.update_ema(product, mid)
        drift = self.update_drift(product, mid)

        # Trend-adjusted fair value
        fair_value = ema + 6.0 * drift

        position = state.position.get(product, 0)
        limit = self.POSITION_LIMIT[product]
        remaining_buy = limit - position
        remaining_sell = position + limit  # max sell size before hitting short limit

        # Signal normalized by spread
        signal = (fair_value - mid) / spread

        # Optional inventory bias: prefer staying long in this trending product
        inventory_bias = -0.0025 * position
        signal += inventory_bias

        # Available top-of-book volumes
        best_ask_vol = abs(order_depth.sell_orders[best_ask]) if best_ask in order_depth.sell_orders else 0
        best_bid_vol = abs(order_depth.buy_orders[best_bid]) if best_bid in order_depth.buy_orders else 0

        # -------------------------
        # BUY LOGIC
        # -------------------------
        # Strong signal -> cross the spread for fills
        if signal > 0.35 and remaining_buy > 0:
            buy_qty = min(12, remaining_buy, best_ask_vol if best_ask_vol > 0 else 12)
            if buy_qty > 0:
                orders.append(Order(product, best_ask, buy_qty))

        # Moderate signal -> passive accumulation
        elif signal > 0.12 and remaining_buy > 0:
            buy_qty = min(8, remaining_buy)
            if buy_qty > 0:
                orders.append(Order(product, best_bid, buy_qty))

        # -------------------------
        # SELL LOGIC
        # -------------------------
        # Only reduce longs / trim exposure; avoid fighting the trend aggressively
        if signal < -0.30 and position > 0:
            sell_qty = min(10, position, best_bid_vol if best_bid_vol > 0 else 10)
            if sell_qty > 0:
                orders.append(Order(product, best_ask, -sell_qty))

        # -------------------------
        # INVENTORY CONTROL
        # -------------------------
        # If too long, trim even if signal is neutral
        if position > 0.75 * limit:
            trim_qty = min(6, position)
            if trim_qty > 0:
                orders.append(Order(product, best_ask, -trim_qty))

        # If position somehow goes negative, repair it quickly
        if position < -10 and remaining_buy > 0:
            repair_qty = min(12, -position, remaining_buy)
            if repair_qty > 0:
                orders.append(Order(product, best_ask, repair_qty))

        result[product] = orders
        return result