import pandas as pd 
import subprocess
import os
import json

# Config
DATE = "2024-02-08"
ARCHIVE = r"C:\Users\ethan\Downloads\prices-2024-02-08.ppmd.7z"
GROUP_ID = "2534" # 2534 = Cosmic Eclipse groupId

GROUP_PATH = f"{DATE}/3/{GROUP_ID}"

EXTRACT_DEST = "Pokemon-Prices"
PRICES_JSON_PATH = os.path.join(EXTRACT_DEST, GROUP_PATH, "prices.json")

# Extraction of Group Prices from ARCHIVE
subprocess.run([r"C:\Program Files\7-Zip\7z.exe", "x", ARCHIVE, GROUP_PATH + "/*", f"-o{EXTRACT_DEST}"])

# Renaming extracted 'prices' file to 'price.json'
extracted_raw_path = os.path.join(EXTRACT_DEST, GROUP_PATH, "prices")
if os.path.exists(extracted_raw_path):
    os.rename(extracted_raw_path, PRICES_JSON_PATH)

# Load 'prices.json'
with open(PRICES_JSON_PATH) as p:
    prices_data = json.load(p)

prices_df = pd.DataFrame(prices_data["results"]) # actual rows are under "results"
prices_df["date"] = DATE

# Load 'ProductsandPrices.csv'
products_df = pd.read_csv('SM-CosmicEclipseProductsAndPrices.csv')

# Join on productId (This is needed because 'prices.json' only has prices listed but has productId)
imp_headers = ["productId", "name", "cleanName", "extRarity", "extNumber"]
merged = pd.merge(
    prices_df,
    products_df[imp_headers],
    on="productId",
    how="left"
)

# Inspect and Sort
print(merged.columns.tolist())
print(merged[["date", "productId", "name", "subTypeName", "marketPrice", "lowPrice"]].head(20))

merged_sorted = merged.sort_values("marketPrice", ascending=False)
print(merged_sorted.head(10))

# Save 
merged.to_csv(f"joined_{DATE}.csv", index=False)
