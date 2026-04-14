import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("/home/sae-itoshi/projects/prosperity-4/Data Capsule/ROUND_1/prices_round_1_day_0.csv", sep=";")

# print(df.columns)
# print(df.head())

pepper = df[df["product"] == "INTARIAN_PEPPER_ROOT"].copy()
pepper = pepper.sort_values("timestamp")

# plot 1 price vs time
plt.figure()
plt.plot(pepper["timestamp"], pepper["mid_price"])
plt.title("Pepper Price vs Time")
plt.show()


# plot 2 spread vs time
pepper["spread"] = pepper["ask_price_1"] - pepper["bid_price_1"]

plt.figure()
plt.plot(pepper["timestamp"], pepper["spread"])
plt.title("Pepper Spread")
plt.show()

# plot 3 Moving Average
window = 20
pepper["ma"] = pepper["mid_price"].rolling(window).mean()

plt.figure()
plt.plot(pepper["timestamp"], pepper["mid_price"])
plt.plot(pepper["timestamp"], pepper["ma"])
plt.title("Pepper Price + MA")
plt.show()

# plot 4 deviation
pepper["dev"] = pepper["mid_price"] - pepper["ma"]

plt.figure()
plt.plot(pepper["timestamp"], pepper["dev"])
plt.title("Pepper Deviation")
plt.show()