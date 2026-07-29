import requests
import time
import sqlite3
import datetime

HEADERS = {"User-Agent": "LeftoverCards_PriceChecker"}

CATEGORY_IDS = [3, 85]
LANGUAGE_CATEGORY = {3: "English", 85: "Japanese"}

DB_PATH = "pokemon_tracker.db"
TODAY = datetime.date.today().isoformat() 

def safe_get(url, headers, retries=3, delay=0.3):
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            time.sleep(delay)  # be polite between every call
            return resp.json()
        except requests.RequestException as e:
            print(f"Attempt {attempt+1} failed for {url}: {e}")
            time.sleep(delay * 2)
    print(f"Giving up on {url}")
    return None

def get_products_and_prices(category_id, group_id):
    products_url = f"https://tcgcsv.com/tcgplayer/{category_id}/{group_id}/products"
    prices_url = f"https://tcgcsv.com/tcgplayer/{category_id}/{group_id}/prices"

    products_data = safe_get(products_url, HEADERS)
    prices_data = safe_get(prices_url, HEADERS)

    if products_data is None or prices_data is None:
        return None, None

    return products_data["results"], prices_data["results"]

def insert_cards(conn, products, set_name, language):
    for row in products:
        conn.execute("""
            INSERT OR IGNORE INTO cards (product_id, name, set_name, rarity, card_number, language) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            row["productId"],
            row["name"],
            set_name,
            row.get("extRarity"),
            row.get("extNumber"),
            language
        ))

def insert_prices(conn, prices, date):
    for row in prices:
        conn.execute("""
            INSERT OR IGNORE INTO price_history (product_id, date, sub_type_name, market_price, low_price, high_price)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            row["productId"],
            date,
            row.get("subTypeName"),
            row.get("marketPrice"),
            row.get("lowPrice"),
            row.get("highPrice")
        ))

 
def main():
    conn = sqlite3.connect(DB_PATH)
 
    for category_id in CATEGORY_IDS:
        language = LANGUAGE_CATEGORY[category_id]
        groups_data = safe_get(f"https://tcgcsv.com/tcgplayer/{category_id}/groups", HEADERS)
 
        if groups_data is None:
            print(f"Skipping category {category_id}, could not fetch groups.")
            continue
 
        groups = groups_data["results"]
        print(f"Category {category_id} ({language}): {len(groups)} groups found.")
 
        for group in groups:
            group_id = group["groupId"]
            set_name = group["name"]
 
            products, prices = get_products_and_prices(category_id, group_id)
            if products is None:
                print(f"Skipping group {group_id} ({set_name}), fetch failed.")
                continue
 
            insert_cards(conn, products, set_name, language)
            insert_prices(conn, prices, TODAY)
            conn.commit()
 
            print(f"  Loaded {set_name}: {len(products)} cards, {len(prices)} price rows.")

    conn.close()
    print("Done.")

if __name__ == "__main__":
    main()