from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import numpy as np


class Trader:

    def __init__(self):
        # Memory
        self.mid_history = []
        self.iv_history: Dict[str, List[float]] = {}

        # Config
        self.lambda_ewma = 0.1
        self.z_window = 40

        self.edge_threshold = 0.02
        self.strong_edge = 0.05

        self.delta_threshold = 5

        self.underlying_limit = 200
        self.voucher_limit = 300

        self.T = 5 / 365  # time to expiry (years)

    # =========================
    # BASIC HELPERS
    # =========================

    def get_mid(self, depth: OrderDepth):
        if not depth.buy_orders or not depth.sell_orders:
            return None
        return (max(depth.buy_orders) + min(depth.sell_orders)) / 2

    def ewma(self, prev, new):
        return self.lambda_ewma * new + (1 - self.lambda_ewma) * prev

    def extract_strike(self, product):
        return int(product.split("_")[1])

    # =========================
    # BLACK-SCHOLES
    # =========================

    def norm_cdf(self, x):
        return 0.5 * (1 + np.math.erf(x / np.sqrt(2)))

    def bs_price(self, S, K, T, sigma):
        if sigma <= 0:
            return max(S - K, 0)

        d1 = (np.log(S / K) + 0.5 * sigma**2 * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)

        return S * self.norm_cdf(d1) - K * self.norm_cdf(d2)

    def implied_vol(self, price, S, K, T):
        sigma = 0.2

        for _ in range(20):
            price_est = self.bs_price(S, K, T, sigma)

            d1 = (np.log(S / K) + 0.5 * sigma**2 * T) / (sigma * np.sqrt(T))
            vega = S * np.sqrt(T) * np.exp(-0.5 * d1**2) / np.sqrt(2 * np.pi)

            if vega < 1e-6:
                break

            sigma -= (price_est - price) / vega
            sigma = max(0.01, min(sigma, 3))

        return sigma

    # =========================
    # SMILE FIT
    # =========================

    def fit_smile(self, strikes, vols, S):
        x = np.array(strikes) - S
        y = np.array(vols)

        if len(x) < 3:
            return None

        return np.polyfit(x, y, 2)

    def smile_vol(self, coeffs, K, S):
        return coeffs[0]*(K-S)**2 + coeffs[1]*(K-S) + coeffs[2]

    # =========================
    # UNDERLYING ENGINE
    # =========================

    def underlying_orders(self, state: TradingState, S_hat):
        orders = []
        depth = state.order_depths["VELVETFRUIT_EXTRACT"]

        pos = state.position.get("VELVETFRUIT_EXTRACT", 0)

        bid = int(S_hat - 2)
        ask = int(S_hat + 2)

        if pos > 0:
            ask -= 1
        elif pos < 0:
            bid += 1

        size = 10

        if pos < self.underlying_limit:
            orders.append(Order("VELVETFRUIT_EXTRACT", bid, size))
        if pos > -self.underlying_limit:
            orders.append(Order("VELVETFRUIT_EXTRACT", ask, -size))

        return orders

    # =========================
    # VOL SURFACE
    # =========================

    def compute_vol_surface(self, state, S):
        strikes = []
        vols = {}
        mids = {}

        for product, depth in state.order_depths.items():
            if "VEV_" not in product:
                continue

            mid = self.get_mid(depth)
            if mid is None:
                continue

            K = self.extract_strike(product)
            iv = self.implied_vol(mid, S, K, self.T)

            strikes.append(K)
            vols[product] = iv
            mids[product] = mid

        return strikes, vols, mids

    # =========================
    # OPTION TRADING
    # =========================

    def option_orders(self, state, S_hat):
        orders_dict = {}

        strikes, vols, mids = self.compute_vol_surface(state, S_hat)

        coeffs = self.fit_smile(strikes, list(vols.values()), S_hat)
        if coeffs is None:
            return {}

        for product, depth in state.order_depths.items():

            if product not in vols:
                continue

            pos = state.position.get(product, 0)
            K = self.extract_strike(product)

            market_iv = vols[product]
            fair_iv = self.smile_vol(coeffs, K, S_hat)

            edge = market_iv - fair_iv

            if abs(edge) < self.edge_threshold:
                continue

            size = int(20 * abs(edge))
            size = min(size, self.voucher_limit - abs(pos))
            if size <= 0:
                continue

            best_bid = max(depth.buy_orders.keys()) if depth.buy_orders else None
            best_ask = min(depth.sell_orders.keys()) if depth.sell_orders else None

            orders = []

            # Passive vs aggressive
            if edge > 0 and best_bid:
                price = best_bid + (1 if abs(edge) < self.strong_edge else 0)
                orders.append(Order(product, price, -size))

            elif edge < 0 and best_ask:
                price = best_ask - (1 if abs(edge) < self.strong_edge else 0)
                orders.append(Order(product, price, size))

            if orders:
                orders_dict[product] = orders

        return orders_dict

    # =========================
    # DELTA HEDGE
    # =========================

    def hedge_delta(self, state):
        total_delta = 0

        for product, pos in state.position.items():
            if "VEV_" in product:
                total_delta += 0.15 * pos
            elif product == "VELVETFRUIT_EXTRACT":
                total_delta += pos

        depth = state.order_depths["VELVETFRUIT_EXTRACT"]

        orders = []

        if total_delta > self.delta_threshold and depth.buy_orders:
            best_bid = max(depth.buy_orders)
            orders.append(Order("VELVETFRUIT_EXTRACT", best_bid, -10))

        elif total_delta < -self.delta_threshold and depth.sell_orders:
            best_ask = min(depth.sell_orders)
            orders.append(Order("VELVETFRUIT_EXTRACT", best_ask, 10))

        return orders

    # =========================
    # MAIN LOOP
    # =========================

    def run(self, state: TradingState):

        result = {}

        # 1. UNDERLYING PRICE
        if "VELVETFRUIT_EXTRACT" not in state.order_depths:
            return {}, 0, ""

        mid = self.get_mid(state.order_depths["VELVETFRUIT_EXTRACT"])
        if mid is None:
            return {}, 0, ""

        if not self.mid_history:
            S_hat = mid
        else:
            S_hat = self.ewma(self.mid_history[-1], mid)

        self.mid_history.append(S_hat)

        # 2. UNDERLYING ORDERS
        result["VELVETFRUIT_EXTRACT"] = self.underlying_orders(state, S_hat)

        # 3. OPTION ORDERS
        option_orders = self.option_orders(state, S_hat)
        for k, v in option_orders.items():
            result[k] = v

        # 4. DELTA HEDGE
        hedge_orders = self.hedge_delta(state)
        if hedge_orders:
            result["VELVETFRUIT_EXTRACT"] += hedge_orders

        return result, 0, ""