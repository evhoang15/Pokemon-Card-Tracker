import sqlite3
import pandas as pd 

# Config
PRODUCTS_CSV = "SM-CosmicEclipseProductsAndPrices.csv"
SET_NAME = "Cosmic Eclipse"
LANGUAGE = "ENGLISH"

conn = sqlite3.connect("pokemon_tracker.db")
df = pd.read_csv(PRODUCTS_CSV)


for index, row in df.iterrows():
    conn.execute("""
    INSERT OR IGNORE INTO cards (product_id, name, set_name, rarity, card_number, language)
        VALUES (?, ?, ?, ?, ?, ?)
""", (
      row["productId"], 
      row["name"], 
      SET_NAME, 
      row["extRarity"], 
      row["extNumber"], 
      LANGUAGE
      ))

cursor = conn.execute("SELECT * FROM cards LIMIT 5")
rows = cursor.fetchall()
for row in rows:
    print(row)

conn.commit()

conn.close()
print(f"Loaded {len(df)} cards from {PRODUCTS_CSV}")