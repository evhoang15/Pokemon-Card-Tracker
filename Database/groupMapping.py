import requests
import subprocess
import sqlite3
import os
import json
import datetime
import pathlib
import time

# Config
SEVEN_ZIP_PATH = r"C:\Program Files\7-Zip\7z.exe"
DB_PATH = pathlib.Path(__file__).parent / "pokemon_tracker.db"
EXTRACT_DIR = pathlib.Path(__file__).parent / "archive_extract"
CATEGORY_IDS = [3, 85]  # 3 = English, 85 = Japanese

HEADERS = {"User-Agent": "LeftoverCards_Archive_PriceChecker"}

MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 5  # multiplied by attempt number


def safe_get(url, **kwargs):
    """requests.get wrapped with retry + backoff for transient network errors
    (connection resets, timeouts, etc). Raises the last error if all retries fail."""
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return requests.get(url, **kwargs)
        except requests.exceptions.ConnectionError as e:
            last_exc = e
            wait = RETRY_BACKOFF_SECONDS * attempt
            print(f"  Connection error on attempt {attempt}/{MAX_RETRIES}: {e}")
            print(f"  Retrying in {wait}s...")
            time.sleep(wait)
        except requests.exceptions.Timeout as e:
            last_exc = e
            wait = RETRY_BACKOFF_SECONDS * attempt
            print(f"  Timeout on attempt {attempt}/{MAX_RETRIES}: {e}")
            print(f"  Retrying in {wait}s...")
            time.sleep(wait)
    print(f"  All {MAX_RETRIES} attempts failed for {url}")
    raise last_exc


def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_group_map (
            product_id INTEGER PRIMARY KEY,
            category_id INTEGER,
            group_id INTEGER
        )
    """)
    conn.commit()


def download_archive(date_str):
    """Download one day's archive. Returns local filepath, or None if not available."""
    url = f"https://tcgcsv.com/archive/tcgplayer/prices-{date_str}.ppmd.7z"
    local_path = f"prices-{date_str}.ppmd.7z"

    resp = safe_get(url, headers=HEADERS, stream=True, timeout=30)
    if resp.status_code != 200:
        print(f"  No archive available for {date_str} (status {resp.status_code}), skipping.")
        return None

    with open(local_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    return local_path


def extract_categories(archive_path, date_str):
    """Extract only the target category folders from the archive."""
    for category_id in CATEGORY_IDS:
        result = subprocess.run([
            SEVEN_ZIP_PATH, "x", archive_path,
            f"{date_str}/{category_id}/*",
            f"-o{EXTRACT_DIR}",
            "-y"  # auto-confirm overwrite
        ], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  7z extraction failed for category {category_id}: {result.stderr}")


def find_price_files(date_str):
    """Walk the extracted folder and find every 'prices' file, returning (categoryId, groupId, filepath)."""
    found = []
    base = os.path.join(EXTRACT_DIR, date_str)
    if not os.path.exists(base):
        print(f"  WARNING: extract base path does not exist: {base}")
        return found

    for category_id in os.listdir(base):
        category_path = os.path.join(base, category_id)
        if not os.path.isdir(category_path):
            continue
        count_before = len(found)
        for group_id in os.listdir(category_path):
            group_path = os.path.join(category_path, group_id)
            price_file = os.path.join(group_path, "prices")
            if os.path.exists(price_file):
                found.append((category_id, group_id, price_file))
        print(f"  Category {category_id}: {len(found) - count_before} price files found")
    return found


def insert_group_mapping_from_file(conn, category_id, group_id, filepath):
    """Read one group's price file and record product_id -> (category_id, group_id)."""
    with open(filepath) as f:
        data = json.load(f)

    rows = data.get("results", [])
    for row in rows:
        conn.execute("""
            INSERT OR IGNORE INTO product_group_map (product_id, category_id, group_id)
            VALUES (?, ?, ?)
        """, (
            row["productId"],
            int(category_id),
            int(group_id)
        ))
    return len(rows)


def process_date(conn, date):
    """Download + extract one date's archive, then record product->group mappings.
    Does NOT touch cards or price_history. Does NOT clean up extracted files afterward,
    so you can spot-check them if needed."""
    date_str = date.isoformat()
    print(f"Processing {date_str}...")

    archive_path = download_archive(date_str)
    if archive_path is None:
        return

    extract_categories(archive_path, date_str)

    price_files = find_price_files(date_str)
    total_rows = 0
    for category_id, group_id, filepath in price_files:
        total_rows += insert_group_mapping_from_file(conn, category_id, group_id, filepath)

    conn.commit()
    print(f"  Mapped {total_rows} product rows across {len(price_files)} groups.")

    # cleanup only the downloaded archive (keep extracted files for inspection)
    os.remove(archive_path)


def check_coverage(conn):
    """Report how many existing cards still have no group_id mapping."""
    cursor = conn.execute("""
        SELECT COUNT(*) FROM cards
        WHERE product_id NOT IN (SELECT product_id FROM product_group_map)
    """)
    unmapped = cursor.fetchone()[0]

    cursor = conn.execute("SELECT COUNT(*) FROM cards")
    total = cursor.fetchone()[0]

    print(f"\nCoverage check: {total - unmapped}/{total} cards mapped, {unmapped} still unmapped.")


def main():
    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)

    # Run for ONE recent date to start. If coverage isn't good enough,
    # add more dates to this list and re-run (INSERT OR IGNORE means it's safe to re-run).
    dates_to_process = [
        datetime.date(2025, 3, 15),
        datetime.date(2025, 11, 1)
    ]

    for date in dates_to_process:
        process_date(conn, date)

    check_coverage(conn)

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()