from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict, Optional, Any


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

    def _normalize_price_key(self, key: Any) -> Optional[int]:
        """
        Prosperity uses int prices as keys.
        Some forked backtesters may wrap prices in dicts.
        """
        if isinstance(key, (int, float)):
            return int(key)

        if isinstance(key, dict):
            for field in ("price", "bid_price", "ask_price"):
                val = key.get(field)
                if isinstance(val, (int, float)):
                    return int(val)

        return None

    def _best_price(self, order_dict: Dict[Any, Any], highest: bool = True) -> Optional[int]:
        if not order_dict:
            return None

        prices = []
        for key in order_dict.keys():
            price = self._normalize_price_key(key)
            if price is not None:
                prices.append(price)

        if not prices:
            return None

        return max(prices) if highest else min(prices)

    def _get_volume(self, order_dict: Dict[Any, Any], price: int) -> int:
        """
        Handles both normal Prosperity format {price: volume}
        and some nested forked formats.
        """
        for key, value in order_dict.items():
            normalized = self._normalize_price_key(key)
            if normalized != price:
                continue

            if isinstance(value, dict):
                total = 0
                for v in value.values():
                    if isinstance(v, (int, float)):
                        total += int(v)
                return abs(total)

            if isinstance(value, (int, float)):
                return abs(int(value))

            return 0

        return 0

    def compute_mid_price(self, order_depth: OrderDepth) -> Optional[float]:
        best_bid = self._best_price(order_depth.buy_orders, highest=True)
        best_ask = self._best_price(order_depth.sell_orders, highest=False)

        if best_bid is None or best_ask is None:
            return None

        return (best_bid + best_ask) / 2.0

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
                self.drift_alpha * raw_drift
                + (1 - self.drift_alpha) * self.drift_estimate[product]
            )
        return self.drift_estimate[product]

    def run(self, state: TradingState):
        result = {}
        conversions = {}
        traderData = state.traderData if state.traderData is not None else ""

        product = "INTARIAN_PEPPER_ROOT"
        orders: List[Order] = []

        if product not in state.order_depths:
            return result, conversions, traderData

        order_depth = state.order_depths[product]
        mid = self.compute_mid_price(order_depth)

        if mid is None:
            result[product] = orders
            return result, conversions, traderData

        best_bid = self._best_price(order_depth.buy_orders, highest=True)
        best_ask = self._best_price(order_depth.sell_orders, highest=False)

        if best_bid is None or best_ask is None:
            result[product] = orders
            return result, conversions, traderData

        best_bid = int(best_bid)
        best_ask = int(best_ask)
        spread = max(1, best_ask - best_bid)

        ema = self.update_ema(product, mid)
        drift = self.update_drift(product, mid)

        # Trend-adjusted fair value
        fair_value = ema + 6.0 * drift

        position = state.position.get(product, 0)
        limit = self.POSITION_LIMIT[product]
        remaining_buy = limit - position

        # Signal normalized by spread
        signal = (fair_value - mid) / spread

        # Small long bias for this trending product
        signal += -0.0025 * position

        # Top-of-book volumes
        best_ask_vol = self._get_volume(order_depth.sell_orders, best_ask)
        best_bid_vol = self._get_volume(order_depth.buy_orders, best_bid)

        # BUY LOGIC
        if signal > 0.35 and remaining_buy > 0:
            buy_qty = min(12, remaining_buy, best_ask_vol if best_ask_vol > 0 else 12)
            if buy_qty > 0:
                orders.append(Order(product, best_ask, buy_qty))

        elif signal > 0.12 and remaining_buy > 0:
            buy_qty = min(8, remaining_buy)
            if buy_qty > 0:
                orders.append(Order(product, best_bid, buy_qty))

        # SELL LOGIC
        if signal < -0.30 and position > 0:
            sell_qty = min(10, position, best_bid_vol if best_bid_vol > 0 else 10)
            if sell_qty > 0:
                orders.append(Order(product, best_ask, -sell_qty))

        # INVENTORY CONTROL
        if position > 0.75 * limit:
            trim_qty = min(6, position)
            if trim_qty > 0:
                orders.append(Order(product, best_ask, -trim_qty))

        if position < -10 and remaining_buy > 0:
            repair_qty = min(12, -position, remaining_buy)
            if repair_qty > 0:
                orders.append(Order(product, best_ask, repair_qty))

        result[product] = orders
        return result, conversions, traderData