import sqlite3
 
conn = sqlite3.connect("pokemon_tracker.db")
 
conn.execute("""
CREATE TABLE cards(
    card_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER UNIQUE,
    name VARCHAR(225),
    set_name VARCHAR(225),
    rarity VARCHAR(225),
    card_number INTEGER,
    language VARCHAR(225)
);
""")
 
conn.execute("""
CREATE TABLE price_history(
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER,
    date TEXT,
    sub_type_name VARCHAR(225),
    market_price REAL,
    low_price REAL,
    high_price REAL,
    FOREIGN KEY (product_id) REFERENCES cards(product_id)
);
""")
 
conn.commit()
conn.close()