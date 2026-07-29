import requests
import subprocess
import sqlite3
import os
import json
import shutil
import datetime
import pathlib

# Config
SEVEN_ZIP_PATH = r"C:\Program Files\7-Zip\7z.exe"
DB_PATH = pathlib.Path(__file__).parent / "pokemon_tracker.db"
EXTRACT_DIR = pathlib.Path(__file__).parent / "archive_extract"          # temp folder, cleaned up per date
CATEGORY_IDS = [3, 85]                    # 3 = English, 85 = Japanese
START_DATE = datetime.date(2025, 1, 1)
END_DATE = datetime.date.today() - datetime.timedelta(days=1)  # archives lag a day

HEADERS = {"User-Agent": "LeftoverCards_Archive_PriceChecker"}


def daterange(start, end):
    """Yield each date from start to end, inclusive."""
    days = (end - start).days
    for i in range(days + 1):
        yield start + datetime.timedelta(days=i)


def download_archive(date_str):
    """Download one day's archive. Returns local filepath, or None if not available."""
    url = f"https://tcgcsv.com/archive/tcgplayer/prices-{date_str}.ppmd.7z"
    local_path = f"prices-{date_str}.ppmd.7z"

    resp = requests.get(url, headers=HEADERS, stream=True, timeout=30)
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


def insert_prices_from_file(conn, filepath, date_str):
    """Load one group's price file into price_history, tagged with the given date."""
    with open(filepath) as f:
        data = json.load(f)

    rows = data.get("results", [])
    for row in rows:
        conn.execute("""
            INSERT OR IGNORE INTO price_history
                (product_id, date, sub_type_name, market_price, low_price, high_price)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            row["productId"],
            date_str,
            row.get("subTypeName"),
            row.get("marketPrice"),
            row.get("lowPrice"),
            row.get("highPrice")
        ))
    return len(rows)


def process_date(conn, date):
    date_str = date.isoformat()
    print(f"Processing {date_str}...")

    archive_path = download_archive(date_str)
    if archive_path is None:
        return

    extract_categories(archive_path, date_str)

    price_files = find_price_files(date_str)
    total_rows = 0
    for category_id, group_id, filepath in price_files:
        total_rows += insert_prices_from_file(conn, filepath, date_str)

    conn.commit()
    print(f"  Loaded {total_rows} price rows across {len(price_files)} groups.")

    # # cleanup to save disk space
    # os.remove(archive_path)
    # date_extract_path = os.path.join(EXTRACT_DIR, date_str)
    # if os.path.exists(date_extract_path):
    #     shutil.rmtree(date_extract_path)


def main():
    # conn = sqlite3.connect(DB_PATH)

    # for date in daterange(START_DATE, END_DATE):
    #     process_date(conn, date)

    # conn.close()
    # print("Backfill complete.")

    conn = sqlite3.connect(DB_PATH)

    test_date = datetime.date(2025, 6, 1)
    process_date(conn, test_date)

    conn.close()
    print("Test run complete.")


if __name__ == "__main__":
    main()