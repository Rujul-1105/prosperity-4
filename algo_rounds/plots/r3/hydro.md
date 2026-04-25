Let me think about every angle before writing this. Here's the complete, final, maximum-alpha strategy for HYDROGEL_PACK.

---

## HYDROGEL_PACK — Maximum Profit Strategy

---

### The Complete Picture of What We Know

Before any strategy, here is every data fact we have and what it implies:

| Observation                       | Implication                                      |
| --------------------------------- | ------------------------------------------------ |
| Fair value = 10000, rock stable   | Never need to guess fair value                   |
| Bot spread = 16 points (±8)       | 16 points of free edge available every timestamp |
| Trade size = 4–5 units per trade  | Quote 5 units to match liquidity exactly         |
| Deviation σ ≈ 5–6 pts, max ±17    | Tight mean reversion, easy to Z-score            |
| Lag-1 ACF = −0.15                 | Bid-ask bounce, MM fills will mean-revert        |
| Cumulative signed vol drifts +100 | Structural bot buyer exists all day              |
| Volume leads price by ~lag        | Volume z-score is a predictive signal            |
| VWAP ≈ mid                        | No hidden execution bias, mid is truth           |
| Macro oscillation ±30–40 pts      | Slow tradeable wave on top of MM                 |

---

### The Three Sources of Profit — Ranked by Expected PnL

**Source 1: Market Making (highest frequency, most reliable)**
**Source 2: Structural Buy Imbalance (medium frequency, high edge)**
**Source 3: Z-Score Macro Wave (low frequency, large per-trade PnL)**

These three are always running simultaneously. They never conflict — they reinforce each other because they operate at different timescales.

---

## SOURCE 1 — Market Making

### Fair Value

```
fair_value = EWMA(mid_price, span=200)
```

Use EWMA not simple MA — it responds faster to genuine shifts while staying smooth. From graph 3, trade VWAP closely tracks EWMA mid, confirming this is the correct anchor.

### Reservation Price (Inventory Adjustment)

```
r = fair_value − q × γ × σ² × (T−t)
```

Where:

- `q` = current net position (positive = long, negative = short)
- `γ` = 0.15 (risk aversion)
- `σ²` = rolling variance of mid returns over 200 ticks (≈ 25–36 from data)
- `T−t` = fraction of day remaining

**What this does:** When you're long 100 units, r drops by ~1.5 points. Your quotes shift down automatically. You sell cheaper and buy dearer — passive inventory management with zero extra logic.

### Optimal Half-Spread

```
δ* = max(  (γ × σ² × (T−t))/2  +  (1/γ) × ln(1 + γ/κ)  ,  floor  )
```

Where:

- `κ` = 4.5 (arrival rate from graph 5)
- `floor` = **3 points** (never quote tighter than this)
- Expected δ\* from data ≈ **5–6 points** → total spread 10–12 points → inside the 16-point bot spread

### Quote Placement

```
bid = r − δ*
ask = r + δ*
quote_size = 5 units per side
```

**Why 5 units:** Bots trade 4–5 units at a time. You match them exactly. Larger quotes sit in the book unfilled and cause adverse selection. Smaller quotes leave money on the table.

### Spread Dynamics Across the Day

| Time   | T−t | σ² (approx) | δ\* (approx) | Behaviour                 |
| ------ | --- | ----------- | ------------ | ------------------------- |
| Open   | 1.0 | 30          | 6.5 pts      | Wide spread, cautious     |
| Midday | 0.5 | 30          | 4.5 pts      | Balanced                  |
| Close  | 0.1 | 30          | 3.0 pts      | Tight, clearing inventory |

**The AS spread automatically handles end-of-day inventory liquidation.** Near close, δ\* approaches the floor, you quote aggressively tight, get filled rapidly, and flatten position. No special end-of-day logic needed.

---

## SOURCE 2 — Structural Buy Imbalance

This is the hidden edge that most teams won't find. Graph 4 shows cumulative signed volume trending persistently from 0 to +100 across the day. This is not random — there is a structural bot buyer operating all day.

### What This Means

The bot is buying ~100 net units per day. This means:

- Price is being pushed slightly upward continuously
- If you lean long, the bot will eventually buy from you (you sell at a premium)
- If you lean short, the bot fights you all day (you lose)

### How to Exploit It

**Step 1 — Measure flow imbalance in real time:**

```
signed_volume = +quantity if buyer-initiated, −quantity if seller-initiated
flow_imbalance = rolling_sum(signed_volume, window=1000 ticks)
flow_z = (flow_imbalance − rolling_mean(flow_imbalance, 5000)) / rolling_std(flow_imbalance, 5000)
```

**Step 2 — Adjust reservation price:**

```
r_final = r + α × flow_z
```

Where α = **1.5 points**

**Effect in practice:**

- flow_z = +1.5 (sustained buying) → r shifts up 2.25 pts → your ask goes up → you sell dearer to the structural buyer
- flow_z = −1.5 (selling pressure) → r shifts down → your bid goes down → you buy cheaper

**Step 3 — Asymmetric quoting when flow is extreme:**

When flow_z > 2.0 (very strong sustained buying):

- **Do not post a bid at all** — don't buy when bots are buying, you'll get stuck long with them
- Post ask only, 2 points tighter than normal (δ\* − 2)
- You become a pure seller into the buying pressure, selling at premium

When flow_z < −2.0 (very strong selling):

- **Do not post an ask** — don't sell when bots are selling
- Post bid only, 2 points tighter
- Buy the dip created by selling bots

This is **the single most important modification** to the strategy. Asymmetric quoting during extreme flow lets you consistently be on the right side of the structural imbalance.

---

## SOURCE 3 — Z-Score Macro Wave

### Signal

```
deviation = mid_price − fair_value
σ_dev = rolling_std(deviation, window=500)
Z = deviation / σ_dev
```

From graph 2: σ_dev ≈ 5–6 points. Max Z observed ≈ ±2.5 before reversion.

### Entries

| Z        | Action            | Size                 | Rationale                                  |
| -------- | ----------------- | -------------------- | ------------------------------------------ |
| Z > 1.8  | Sell aggressively | 15 units             | 1.8σ excursion, high reversion probability |
| Z > 2.5  | Add sell          | +15 units (total 30) | Extreme, near certain reversion            |
| Z < −1.8 | Buy aggressively  | 15 units             |                                            |
| Z < −2.5 | Add buy           | +15 units (total 30) |                                            |

**Note: threshold is 1.8, not 2.0.** From graph 2, the smoothed deviation rarely exceeds 10 points (≈ 1.8σ). Waiting for 2.0 means missing most of the signal.

### Exits

```
Exit long when Z > −0.3
Exit short when Z < +0.3
```

Exit very close to zero to capture the full move. The mean reversion is fast (negative ACF confirms this) so you won't sit in a trade long.

### Interaction With Flow Signal

| Z signal       | Flow signal               | Combined action                                         |
| -------------- | ------------------------- | ------------------------------------------------------- |
| Z > 1.8 (sell) | flow_z > 0 (bots buying)  | **Do not take Z trade** — fighting the structural buyer |
| Z > 1.8 (sell) | flow_z < 0 (bots selling) | **Take full Z trade** — both signals aligned            |
| Z < −1.8 (buy) | flow_z > 0 (bots buying)  | **Take full Z trade** — both aligned                    |
| Z < −1.8 (buy) | flow_z < 0 (bots selling) | **Do not take Z trade** — fighting flow                 |

**This filter alone will significantly improve Z-score PnL** by eliminating trades that go against the structural buyer.

---

## Position Management — The Full System

### Position Budget Allocation

```
Total limit: ±180 (hard cap, never breach)

Allocated to MM inventory:     ±80 units
Allocated to directional Z:    ±30 units
Buffer for flow asymmetry:     ±70 units
```

These aren't rigid silos — they're soft targets. The hard cap of ±180 is the only enforced constraint.

### Real-Time Position Check (every timestamp)

```
available_long  = 180 − current_position
available_short = 180 + current_position

→ MM bid size  = min(5, available_long)
→ MM ask size  = min(5, available_short)
→ Z buy size   = min(15, available_long)
→ Z sell size  = min(15, available_short)
```

### End-of-Day Flattening

```
If T−t < 0.05 (last 5% of day, ~50,000 timestamps):
    - Stop Z-score entries entirely
    - Stop one-sided flow quoting
    - AS spread narrows automatically (T−t → 0)
    - If position > +20: place aggressive market sell for (position − 5) units
    - If position < −20: place aggressive market buy for (|position| − 5) units
    - Target: end day at ±5 or closer
```

---

## The Decision Tree — Every Timestamp

```
STEP 1: Compute signals
    σ = rolling_std(log_returns, 200)
    fair_value = EWMA(mid, span=200)
    q = current_position
    T_t = time_remaining / day_length
    deviation = mid - fair_value
    Z = deviation / rolling_std(deviation, 500)
    flow_z = flow_imbalance_z_score

STEP 2: Compute reservation price
    r = fair_value - q × 0.15 × σ² × T_t
    r_final = r + 1.5 × flow_z

STEP 3: Compute spread
    δ* = max(AS_formula(γ=0.15, σ, T_t, κ=4.5), 3.0)

STEP 4: Check flow asymmetry
    if flow_z > 2.0:
        skip bid, post ask at (r_final + δ* - 2), size=5
    elif flow_z < -2.0:
        skip ask, post bid at (r_final - δ* + 2), size=5
    else:
        post both: bid=(r_final - δ*), ask=(r_final + δ*), size=5

STEP 5: Check Z-score
    if |Z| > 1.8 AND flow confirms:
        place directional order, size=15
        if |Z| > 2.5: additional 15 units
    if holding directional position AND |Z| < 0.3:
        exit position

STEP 6: End-of-day check
    if T_t < 0.05: flatten as described above

STEP 7: Enforce hard cap
    never place order that would breach ±180
```

---

## Final Parameter Table

| Parameter                | Value                 | Source                     |
| ------------------------ | --------------------- | -------------------------- |
| EWMA span                | 200                   | Graph 3, VWAP tracking     |
| γ (risk aversion)        | 0.15                  | AS model, tune in backtest |
| κ (arrival rate)         | 4.5                   | Graph 5                    |
| δ\* floor                | 3 points              | Minimum viable spread      |
| Quote size               | 5 units               | Graph 5 trade volume       |
| Flow window              | 1000 ticks            | Graph 4 persistence        |
| Flow α                   | 1.5 points            | Tune in backtest           |
| Flow asymmetry threshold | ±2.0                  | Extreme flow signal        |
| Z-score σ window         | 500 ticks             | Graph 2                    |
| Z entry                  | ±1.8                  | Graph 2 max observed       |
| Z add                    | ±2.5                  | Extreme extension          |
| Z exit                   | ±0.3                  | Near zero, full capture    |
| Directional size         | 15 units (+15 at 2.5) | Position budget            |
| Hard cap                 | ±180                  | Rules                      |
| End-of-day trigger       | T−t < 0.05            |                            |

---

## What Every Profit Dollar Comes From

| Source              | Mechanism                        | Expected contribution                |
| ------------------- | -------------------------------- | ------------------------------------ |
| MM spread capture   | 10–12 pts × 5 units × many fills | **Largest, most consistent**         |
| Flow asymmetry      | Selling dear to structural buyer | **Second largest, passive**          |
| Z-score reversions  | 15–30 units × 10–20 pt moves     | **Highest per-trade, less frequent** |
| AS spread narrowing | More fills near close            | **Small but free**                   |

---

**This is the complete, final, maximum-alpha HYDROGEL_PACK strategy.** Every graph has been used. Every signal is justified by data. Ready for VEV whenever you are.
