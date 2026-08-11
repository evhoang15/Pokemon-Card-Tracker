import requests
import mysql.connector
import time

# ---- Config ----
MYSQL_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",  # fill in your local MySQL password
    "database": "leftover_cardsdb"  # fill in your actual db name
}

HEADERS = {"User-Agent": "LeftoverCards_Archive_PriceChecker"}
MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 5
PAUSE_BETWEEN_GROUPS_SECONDS = 0.5  # be polite to tcgcsv's server


def safe_get(url, **kwargs):
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return requests.get(url, **kwargs)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_exc = e
            wait = RETRY_BACKOFF_SECONDS * attempt
            print(f"  Network error on attempt {attempt}/{MAX_RETRIES}: {e}")
            print(f"  Retrying in {wait}s...")
            time.sleep(wait)
    print(f"  All {MAX_RETRIES} attempts failed for {url}")
    raise last_exc


def has_number_field(extended_data):
    """Signal that a product is a real card, not a sealed product."""
    for field in extended_data or []:
        if field.get("name") == "Number":
            return True
    return False


def is_code_card(name):
    """Digital code SKUs - not physical inventory, exclude entirely."""
    return name.strip().startswith("Code Card -")


def ensure_progress_table(mysql_conn):
    cursor = mysql_conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS migration_progress (
            table_name VARCHAR(50) PRIMARY KEY,
            last_id BIGINT NOT NULL DEFAULT 0
        )
    """)
    mysql_conn.commit()


def get_last_group_id(mysql_conn):
    cursor = mysql_conn.cursor()
    cursor.execute("SELECT last_id FROM migration_progress WHERE table_name = 'sealed_products'")
    row = cursor.fetchone()
    return row[0] if row else 0


def set_last_group_id(mysql_conn, group_id):
    cursor = mysql_conn.cursor()
    cursor.execute("""
        INSERT INTO migration_progress (table_name, last_id) VALUES ('sealed_products', %s)
        ON DUPLICATE KEY UPDATE last_id = %s
    """, (group_id, group_id))
    mysql_conn.commit()


def get_groups_to_process(mysql_conn, last_group_id):
    """All (group_id, category_id) from sets, in order, resuming after last_group_id."""
    cursor = mysql_conn.cursor()
    cursor.execute("""
        SELECT group_id, category_id FROM sets
        WHERE group_id > %s
        ORDER BY group_id
    """, (last_group_id,))
    return cursor.fetchall()


def fetch_products(category_id, group_id):
    url = f"https://tcgcsv.com/tcgplayer/{category_id}/{group_id}/products"
    resp = safe_get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json().get("results", [])


def main():
    mysql_conn = mysql.connector.connect(**MYSQL_CONFIG)
    ensure_progress_table(mysql_conn)

    last_group_id = get_last_group_id(mysql_conn)
    groups = get_groups_to_process(mysql_conn, last_group_id)
    print(f"Resuming from group_id > {last_group_id}. {len(groups)} groups to process.")

    total_inserted = 0
    total_code_cards_skipped = 0

    cursor = mysql_conn.cursor()

    for i, (group_id, category_id) in enumerate(groups, start=1):
        try:
            products = fetch_products(category_id, group_id)
        except Exception as e:
            print(f"  FAILED group {group_id} (category {category_id}) after retries: {e}")
            print(f"  Stopping here - rerun the script to resume from this group.")
            break

        batch = []
        for p in products:
            if has_number_field(p.get("extendedData")):
                continue  # it's a card, not our concern here

            name = p.get("name", "")
            if is_code_card(name):
                total_code_cards_skipped += 1
                continue

            batch.append((p["productId"], name, group_id, None))  # product_type left NULL for manual review

        if batch:
            cursor.executemany("""
                INSERT IGNORE INTO sealed_products (product_id, name, group_id, product_type)
                VALUES (%s, %s, %s, %s)
            """, batch)
            mysql_conn.commit()
            total_inserted += len(batch)

        set_last_group_id(mysql_conn, group_id)

        if i % 25 == 0:
            print(f"  Processed {i}/{len(groups)} groups. {total_inserted} sealed products inserted so far.")

        time.sleep(PAUSE_BETWEEN_GROUPS_SECONDS)

    print(f"\nDone. {total_inserted} sealed products inserted, {total_code_cards_skipped} code cards skipped.")
    mysql_conn.close()


if __name__ == "__main__":
    main()