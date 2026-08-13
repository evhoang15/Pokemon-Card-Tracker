import mysql.connector
from werkzeug.security import generate_password_hash
import getpass

MYSQL_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "TheBeatles-1970!",  # fill in your local MySQL password
    "database": "leftover_cardsdb"
}


def create_user(conn):
    username = input("Username: ").strip()
    password = getpass.getpass("Password (hidden as you type): ")
    confirm = getpass.getpass("Confirm password: ")

    if len(password) < 10:
        print("Password must be at least 10 characters. Aborting.")
        return None

    if password != confirm:
        print("Passwords don't match. Aborting.")
        return None

    is_admin = input("Is this an admin account? (y/n): ").strip().lower() == "y"
    password_hash = generate_password_hash(password)

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (username, password_hash, is_admin)
        VALUES (%s, %s, %s)
    """, (username, password_hash, is_admin))
    conn.commit()

    user_id = cursor.lastrowid
    print(f"Created user '{username}' (user_id={user_id}, admin={is_admin})")
    return user_id


def create_vendor(conn):
    name = input("Vendor name (e.g. your name): ").strip()

    link_choice = input("Link this vendor to an existing user account? (y/n): ").strip().lower()
    linked_user_id = None
    if link_choice == "y":
        linked_user_id = input("Enter the user_id to link: ").strip()
        linked_user_id = int(linked_user_id) if linked_user_id else None

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO vendors (name, linked_user_id)
        VALUES (%s, %s)
    """, (name, linked_user_id))
    conn.commit()

    vendor_id = cursor.lastrowid
    print(f"Created vendor '{name}' (vendor_id={vendor_id})")
    return vendor_id


def main():
    conn = mysql.connector.connect(**MYSQL_CONFIG)

    while True:
        print("\nWhat do you want to create?")
        print("  1. User account (login)")
        print("  2. Vendor record (whose cards)")
        print("  3. Quit")
        choice = input("> ").strip()

        if choice == "1":
            create_user(conn)
        elif choice == "2":
            create_vendor(conn)
        elif choice == "3":
            break
        else:
            print("Invalid choice.")

    conn.close()


if __name__ == "__main__":
    main()