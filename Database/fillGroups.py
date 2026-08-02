import requests
import sqlite3
import pathlib
import time

# Config
DB_PATH = pathlib.Path(__file__).parent / "pokemon_tracker.db"
CATEGORY_IDS = [3, 85]  # 3 = English, 85 = Japanese

HEADERS = {"User-Agent": "LeftoverCards_Archive_PriceChecker"}

MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 5


def safe_get(url, **kwargs):
    """requests.get wrapped with retry + backoff for transient network errors."""
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


def normalize(name):
    """Normalize a set name for comparison: trim whitespace, lowercase."""
    if name is None:
        return ""
    return name.strip().lower()


def fetch_groups(category_id):
    """Fetch the full live groups listing for a category. Returns list of dicts."""
    url = f"https://tcgcsv.com/tcgplayer/{category_id}/groups"
    resp = safe_get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("results", [])


def build_set_lookup():
    """Build a {(category_id, normalized_set_name): group_id} lookup from tcgcsv's live groups data."""
    lookup = {}
    for category_id in CATEGORY_IDS:
        print(f"Fetching groups for category {category_id}...")
        groups = fetch_groups(category_id)
        print(f"  {len(groups)} groups found")
        for group in groups:
            key = (category_id, normalize(group.get("name")))
            lookup[key] = group.get("groupId")
    return lookup


def get_unmapped_cards(conn):
    """Return (product_id, set_name, language) for cards not yet in product_group_map."""
    cursor = conn.execute("""
        SELECT product_id, set_name, language
        FROM cards
        WHERE product_id NOT IN (SELECT product_id FROM product_group_map)
    """)
    return cursor.fetchall()


LANGUAGE_TO_CATEGORY = {
    "english": 3,
    "japanese": 85,
}


def main():
    conn = sqlite3.connect(DB_PATH)

    set_lookup = build_set_lookup()

    unmapped = get_unmapped_cards(conn)
    print(f"\n{len(unmapped)} unmapped cards to resolve.")

    matched = 0
    unmatched_rows = []

    for product_id, set_name, language in unmapped:
        category_id = LANGUAGE_TO_CATEGORY.get(normalize(language))
        if category_id is None:
            unmatched_rows.append((product_id, set_name, language))
            continue

        key = (category_id, normalize(set_name))
        group_id = set_lookup.get(key)

        if group_id is None:
            unmatched_rows.append((product_id, set_name, language))
            continue

        conn.execute("""
            INSERT OR IGNORE INTO product_group_map (product_id, category_id, group_id)
            VALUES (?, ?, ?)
        """, (product_id, category_id, group_id))
        matched += 1

    conn.commit()

    print(f"\nMatched and inserted: {matched}")
    print(f"Still unmatched: {len(unmatched_rows)}")

    if unmatched_rows:
        print("\nUnmatched cards (product_id, set_name, language):")
        for row in unmatched_rows[:50]:  # cap output so it doesn't flood the terminal
            print(f"  {row}")
        if len(unmatched_rows) > 50:
            print(f"  ...and {len(unmatched_rows) - 50} more")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()