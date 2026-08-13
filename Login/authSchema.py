import mysql.connector

MYSQL_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "TheBeatles-1970!",  # fill in your local MySQL password
    "database": "leftover_cardsdb"
}


def column_exists(conn, table, column):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s AND column_name = %s
    """, (MYSQL_CONFIG["database"], table, column))
    return cursor.fetchone()[0] > 0


def main():
    conn = mysql.connector.connect(**MYSQL_CONFIG)
    cursor = conn.cursor()

    print("Creating users table (if not exists)...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            is_admin BOOLEAN NOT NULL DEFAULT FALSE,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    print("Creating vendors table (if not exists)...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vendors (
            vendor_id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            linked_user_id INT,
            FOREIGN KEY (linked_user_id) REFERENCES users(user_id)
        )
    """)
    conn.commit()

    for table in ("inventory_lots", "sales"):
        if not column_exists(conn, table, "entered_by_user_id"):
            print(f"Adding entered_by_user_id to {table}...")
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN entered_by_user_id INT")
            conn.commit()
        else:
            print(f"{table}.entered_by_user_id already exists.")

    if not column_exists(conn, "inventory_lots", "vendor_id"):
        print("Adding vendor_id to inventory_lots...")
        cursor.execute("ALTER TABLE inventory_lots ADD COLUMN vendor_id INT")
        conn.commit()
    else:
        print("inventory_lots.vendor_id already exists.")

    conn.close()
    print("\nSchema setup complete.")


if __name__ == "__main__":
    main()