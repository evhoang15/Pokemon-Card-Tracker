import sqlite3
import mysql.connector
import pathlib

# ---- Config ----
SQLITE_DB_PATH = pathlib.Path(__file__).parent / "pokemon_tracker.db"

MYSQL_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",  # fill in your local MySQL password
    "database": "leftover_cardsdb"  # fill in your actual db name
}

BATCH_SIZE = 20000


def normalize(value):
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped != "" else None


def ensure_progress_table(mysql_conn):
    cursor = mysql_conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS migration_progress (
            table_name VARCHAR(50) PRIMARY KEY,
            last_id BIGINT NOT NULL DEFAULT 0
        )
    """)
    mysql_conn.commit()


def get_last_id(mysql_conn, table_name):
    cursor = mysql_conn.cursor()
    cursor.execute("SELECT last_id FROM migration_progress WHERE table_name = %s", (table_name,))
    row = cursor.fetchone()
    return row[0] if row else 0


def set_last_id(mysql_conn, table_name, last_id):
    cursor = mysql_conn.cursor()
    cursor.execute("""
        INSERT INTO migration_progress (table_name, last_id) VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE last_id = %s
    """, (table_name, last_id, last_id))
    mysql_conn.commit()


def load_lookup(mysql_conn, table, id_col, name_col):
    """Generic {name: id} lookup builder from a MySQL table."""
    cursor = mysql_conn.cursor()
    cursor.execute(f"SELECT {id_col}, {name_col} FROM {table}")
    return {name: id_val for id_val, name in cursor.fetchall()}


def load_product_group_map(sqlite_conn):
    """{product_id: group_id} from SQLite."""
    rows = sqlite_conn.execute("SELECT product_id, group_id FROM product_group_map").fetchall()
    return {product_id: group_id for product_id, group_id in rows}


def migrate_cards(sqlite_conn, mysql_conn, group_map, rarity_lookup):
    table_name = "cards"
    last_id = get_last_id(mysql_conn, table_name)
    print(f"Resuming cards migration from product_id > {last_id}")

    total_migrated = 0
    total_skipped_no_group = 0

    while True:
        rows = sqlite_conn.execute("""
            SELECT product_id, name, rarity, card_number
            FROM cards
            WHERE product_id > ?
            ORDER BY product_id
            LIMIT ?
        """, (last_id, BATCH_SIZE)).fetchall()

        if not rows:
            break

        batch = []
        for product_id, name, rarity, card_number in rows:
            group_id = group_map.get(product_id)
            if group_id is None:
                total_skipped_no_group += 1
                continue

            rarity_name = normalize(rarity)
            rarity_id = rarity_lookup.get(rarity_name) if rarity_name else None

            batch.append((product_id, name, group_id, rarity_id, card_number))

        if batch:
            cursor = mysql_conn.cursor()
            cursor.executemany("""
                INSERT IGNORE INTO cards (product_id, name, group_id, rarity_id, card_number)
                VALUES (%s, %s, %s, %s, %s)
            """, batch)
            mysql_conn.commit()
            total_migrated += len(batch)

        last_id = rows[-1][0]
        set_last_id(mysql_conn, table_name, last_id)
        print(f"  cards: {total_migrated} migrated so far (up to product_id {last_id})")

    print(f"cards migration complete: {total_migrated} migrated, {total_skipped_no_group} skipped (no group_id)")


def migrate_price_history(sqlite_conn, mysql_conn, sub_type_lookup):
    table_name = "price_history"
    last_id = get_last_id(mysql_conn, table_name)
    print(f"Resuming price_history migration from history_id > {last_id}")

    total_migrated = 0

    while True:
        rows = sqlite_conn.execute("""
            SELECT history_id, product_id, date, sub_type_name, market_price, low_price, high_price
            FROM price_history
            WHERE history_id > ?
            ORDER BY history_id
            LIMIT ?
        """, (last_id, BATCH_SIZE)).fetchall()

        if not rows:
            break

        batch = []
        for history_id, product_id, date, sub_type_name, market_price, low_price, high_price in rows:
            sub_type_clean = normalize(sub_type_name)
            sub_type_id = sub_type_lookup.get(sub_type_clean) if sub_type_clean else None

            batch.append((product_id, date, sub_type_id, market_price, low_price, high_price))

        if batch:
            cursor = mysql_conn.cursor()
            cursor.executemany("""
                INSERT IGNORE INTO price_history
                    (product_id, date, sub_type_id, market_price, low_price, high_price)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, batch)
            mysql_conn.commit()
            total_migrated += len(batch)

        last_id = rows[-1][0]
        set_last_id(mysql_conn, table_name, last_id)
        print(f"  price_history: {total_migrated} migrated so far (up to history_id {last_id})")

    print(f"price_history migration complete: {total_migrated} migrated")


def main():
    sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
    mysql_conn = mysql.connector.connect(**MYSQL_CONFIG)

    ensure_progress_table(mysql_conn)

    print("Loading lookups...")
    group_map = load_product_group_map(sqlite_conn)
    rarity_lookup = load_lookup(mysql_conn, "rarities", "rarity_id", "rarity_name")
    sub_type_lookup = load_lookup(mysql_conn, "sub_types", "sub_type_id", "sub_type_name")
    print(f"  {len(group_map)} product->group mappings, {len(rarity_lookup)} rarities, {len(sub_type_lookup)} sub_types")

    print("\n=== Migrating cards ===")
    migrate_cards(sqlite_conn, mysql_conn, group_map, rarity_lookup)

    print("\n=== Migrating price_history ===")
    migrate_price_history(sqlite_conn, mysql_conn, sub_type_lookup)

    sqlite_conn.close()
    mysql_conn.close()
    print("\nStage 2 complete.")


if __name__ == "__main__":
    main()