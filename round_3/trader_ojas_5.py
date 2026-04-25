from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import numpy as np


class Trader:

    def __init__(self):
        # =========================
        # MEMORY
        # =========================
        self.mid_history = []

        # =========================
        # CONFIG
        # =========================
        self.lambda_ewma = 0.1
        self.T = 5 / 365

        # thresholds
        self.edge_threshold = 0.02
        self.strong_edge = 0.05

        # limits
        self.VEV_LIMIT = 300
        self.VEV_SOFT = 150
        self.UND_LIMIT = 200
        self.UND_SOFT = 100

        # top-k trades
        self.TOP_K = 3

    # =========================
    # BASIC HELPERS
    # =========================

    def get_mid(self, depth: OrderDepth):
        if not depth.buy_orders or not depth.sell_orders:
            return None
        return (max(depth.buy_orders) + min(depth.sell_orders)) / 2

    def ewma(self, prev, new):
        return self.lambda_ewma * new + (1 - self.lambda_ewma) * prev

    def strike(self, product):
        return int(product.split("_")[1])

    # =========================
    # INVENTORY CONTROL
    # =========================

    def inv_scale(self, pos, soft_limit):
        return max(0.2, 1 - abs(pos) / soft_limit)

    # =========================
    # BLACK-SCHOLES
    # =========================

    def norm_cdf(self, x):
        return 0.5 * (1 + np.math.erf(x / np.sqrt(2)))

    def bs_price(self, S, K, T, sigma):
        if sigma <= 0:
            return max(S - K, 0)

        d1 = (np.log(S/K) + 0.5*sigma**2*T) / (sigma*np.sqrt(T))
        d2 = d1 - sigma*np.sqrt(T)

        return S*self.norm_cdf(d1) - K*self.norm_cdf(d2)

    def implied_vol(self, price, S, K, T):
        sigma = 0.2
        for _ in range(20):
            d1 = (np.log(S/K) + 0.5*sigma**2*T) / (sigma*np.sqrt(T))
            vega = S*np.sqrt(T)*np.exp(-0.5*d1**2)/np.sqrt(2*np.pi)

            if vega < 1e-6:
                break

            price_est = self.bs_price(S, K, T, sigma)
            sigma -= (price_est - price)/vega
            sigma = max(0.01, min(sigma, 3))

        return sigma

    # =========================
    # STRIKE WEIGHT (ATM FOCUS)
    # =========================

    def strike_weight(self, K, S):
        return 1 / (1 + abs(K - S) / 100)

    # =========================
    # VOL SURFACE
    # =========================

    def compute_surface(self, state, S):
        strikes, vols = [], {}
        for product, depth in state.order_depths.items():
            if "VEV_" not in product:
                continue

            mid = self.get_mid(depth)
            if mid is None:
                continue

            K = self.strike(product)
            iv = self.implied_vol(mid, S, K, self.T)

            strikes.append(K)
            vols[product] = iv

        return strikes, vols

    def fit_smile(self, strikes, vols, S):
        x = np.array(strikes) - S
        y = np.array(vols)

        if len(x) < 3:
            return None

        weights = np.array([self.strike_weight(K, S) for K in strikes])

        coeffs = np.polyfit(x, y, 2, w=weights)

        # enforce smile (convex)
        if coeffs[0] < 0:
            return None

        return coeffs

    def smile_vol(self, coeffs, K, S):
        return coeffs[0]*(K-S)**2 + coeffs[1]*(K-S) + coeffs[2]

    # =========================
    # OPTION ENGINE
    # =========================

    def option_orders(self, state, S):
        result = {}

        strikes, vols = self.compute_surface(state, S)
        coeffs = self.fit_smile(strikes, list(vols.values()), S)

        if coeffs is None:
            return result

        edges = []

        # compute edges
        for product, depth in state.order_depths.items():
            if product not in vols:
                continue

            if product in ["VEV_4000", "VEV_4500"]:
                continue  # skip bad strikes

            K = self.strike(product)
            market_iv = vols[product]
            fair_iv = self.smile_vol(coeffs, K, S)

            edge = market_iv - fair_iv
            weight = self.strike_weight(K, S)

            weighted_edge = edge * weight

            edges.append((product, weighted_edge, edge, K))

        # select top-k
        edges = sorted(edges, key=lambda x: abs(x[1]), reverse=True)[:self.TOP_K]

        for product, w_edge, edge, K in edges:

            if abs(edge) < self.edge_threshold:
                continue

            depth = state.order_depths[product]
            pos = state.position.get(product, 0)

            scale = self.inv_scale(pos, self.VEV_SOFT)

            size = int(10 * abs(edge) * self.strike_weight(K, S) * scale)
            size = min(size, self.VEV_LIMIT - abs(pos))

            if size <= 0:
                continue

            best_bid = max(depth.buy_orders) if depth.buy_orders else None
            best_ask = min(depth.sell_orders) if depth.sell_orders else None

            orders = []

            # execution
            if edge > 0 and best_bid:
                price = best_bid + (1 if abs(edge) < self.strong_edge else 0)
                orders.append(Order(product, price, -size))

            elif edge < 0 and best_ask:
                price = best_ask - (1 if abs(edge) < self.strong_edge else 0)
                orders.append(Order(product, price, size))

            if orders:
                result[product] = orders

        return result

    # =========================
    # UNDERLYING ENGINE
    # =========================

    def underlying_orders(self, state, S, S_hat):
        result = []
        depth = state.order_depths["VELVETFRUIT_EXTRACT"]

        pos = state.position.get("VELVETFRUIT_EXTRACT", 0)
        scale = self.inv_scale(pos, self.UND_SOFT)

        dev = S - S_hat

        best_bid = max(depth.buy_orders) if depth.buy_orders else None
        best_ask = min(depth.sell_orders) if depth.sell_orders else None

        size = int(10 * scale)

        # mean reversion
        if dev > 2.5 and best_bid:
            result.append(Order("VELVETFRUIT_EXTRACT", best_bid, -size))

        elif dev < -2.5 and best_ask:
            result.append(Order("VELVETFRUIT_EXTRACT", best_ask, size))

        return result

    # =========================
    # MAIN
    # =========================

    def run(self, state: TradingState):

        result = {}

        # underlying mid
        if "VELVETFRUIT_EXTRACT" not in state.order_depths:
            return {}, 0, ""

        mid = self.get_mid(state.order_depths["VELVETFRUIT_EXTRACT"])
        if mid is None:
            return {}, 0, ""

        # EWMA
        if not self.mid_history:
            S_hat = mid
        else:
            S_hat = self.ewma(self.mid_history[-1], mid)

        self.mid_history.append(S_hat)

        # =========================
        # OPTIONS
        # =========================
        option_orders = self.option_orders(state, S_hat)
        for k, v in option_orders.items():
            result[k] = v

        # =========================
        # UNDERLYING
        # =========================
        und_orders = self.underlying_orders(state, mid, S_hat)
        if und_orders:
            result["VELVETFRUIT_EXTRACT"] = und_orders

        return result, 0, ""