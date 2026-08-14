from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from werkzeug.security import check_password_hash
import mysql.connector
import os 
from datetime import timedelta
import logging
from logging.handlers import RotatingFileHandler

app = Flask(__name__)
if not app.debug:
    handler = RotatingFileHandler("app_errors.log", maxBytes=1_000_000, backupCount=3)
    handler.setLevel(logging.ERROR)
    formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]")
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.ERROR)
app.secret_key = ""
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)

# ---- Config ----
MYSQL_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": os.environ["MYSQL_PASSWORD"], 
    "database": os.environ["MYSQL_DATABASE"]
}


def get_db():
    return mysql.connector.connect(**MYSQL_CONFIG)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        if not session.get("is_admin"):
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT user_id, password_hash, is_admin FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    conn.close()

    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Invalid username or password")

    session["user_id"] = user["user_id"]
    session.permanent = True
    session["is_admin"] = bool(user["is_admin"])
    return redirect(url_for("home"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------------------------------------------------------------------
# Page routes (render HTML - these are the parts that get replaced by React later)
# ---------------------------------------------------------------------------

@app.route("/")
@login_required
def home():
    return render_template("inventory.html")


@app.route("/purchase")
@login_required
def purchase_page():
    return render_template("purchase.html")


@app.route("/sale")
@login_required
def sale_page():
    return render_template("sale.html")


# ---------------------------------------------------------------------------
# API routes (JSON only - these are the ones that survive the React rewrite)
# ---------------------------------------------------------------------------

@app.route("/api/search_products")
@login_required
def search_products():
    """Search cards or sealed_products by name. ?q=charizard&item_type=card"""
    query = request.args.get("q", "").strip()
    item_type = request.args.get("item_type", "card")

    if len(query) < 2:
        return jsonify([])

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    like_pattern = f"%{query}%"

    if item_type == "card":
        cursor.execute("""
            SELECT c.product_id, c.name, c.card_number, s.set_name, r.rarity_name
            FROM cards c
            JOIN sets s ON s.group_id = c.group_id
            LEFT JOIN rarities r ON r.rarity_id = c.rarity_id
            WHERE c.name LIKE %s
            ORDER BY c.name
            LIMIT 20
        """, (like_pattern,))
    else:
        cursor.execute("""
            SELECT sp.product_id, sp.name, s.set_name, sp.product_type
            FROM sealed_products sp
            JOIN sets s ON s.group_id = sp.group_id
            WHERE sp.name LIKE %s
            ORDER BY sp.name
            LIMIT 20
        """, (like_pattern,))

    results = cursor.fetchall()
    conn.close()
    return jsonify(results)


@app.route("/api/conditions")
@login_required
def get_conditions():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT condition_id, condition_name FROM conditions ORDER BY condition_id")
    results = cursor.fetchall()
    conn.close()
    return jsonify(results)


@app.route("/api/purchase", methods=["POST"])
@login_required
def log_purchase():
    data = request.get_json()

    required = ["item_type", "product_id", "purchase_price", "purchase_date", "quantity_purchased"]
    missing = [f for f in required if f not in data or data[f] in (None, "")]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    item_type = data["item_type"]
    if item_type not in ("card", "sealed_product"):
        return jsonify({"error": "item_type must be 'card' or 'sealed_product'"}), 400

    quantity = int(data["quantity_purchased"])

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO inventory_lots
            (item_type, product_id, condition_id, purchase_price, purchase_date,
             quantity_purchased, quantity_remaining)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        item_type,
        data["product_id"],
        data.get("condition_id"),  # nullable
        data["purchase_price"],
        data["purchase_date"],
        quantity,
        quantity  # quantity_remaining starts equal to quantity_purchased
    ))
    conn.commit()
    lot_id = cursor.lastrowid
    conn.close()

    return jsonify({"success": True, "lot_id": lot_id})


@app.route("/api/lots")
@login_required
def get_open_lots():
    """Lots with quantity_remaining > 0, for the sale page to pick from."""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT
            l.lot_id, l.item_type, l.product_id, l.quantity_remaining,
            l.purchase_price, l.purchase_date, c.condition_name,
            COALESCE(cards.name, sp.name) AS product_name,
            cards.card_number, r.rarity_name
        FROM inventory_lots l
        LEFT JOIN conditions c ON c.condition_id = l.condition_id
        LEFT JOIN cards ON l.item_type = 'card' AND cards.product_id = l.product_id
        LEFT JOIN sealed_products sp ON l.item_type = 'sealed_product' AND sp.product_id = l.product_id
        LEFT JOIN rarities r ON r.rarity_id = cards.rarity_id
        WHERE l.quantity_remaining > 0
        ORDER BY l.purchase_date DESC
    """)
    results = cursor.fetchall()
    conn.close()
    return jsonify(results)


@app.route("/api/sale", methods=["POST"])
@login_required
def log_sale():
    data = request.get_json()

    required = ["lot_id", "quantity_sold", "sale_price", "sale_date"]
    missing = [f for f in required if f not in data or data[f] in (None, "")]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    lot_id = data["lot_id"]
    quantity_sold = int(data["quantity_sold"])

    conn = get_db()
    cursor = conn.cursor()

    # Atomic: only decrements if enough stock is still available RIGHT NOW.
    # If two requests race, only one of them can match this WHERE clause and succeed.
    cursor.execute("""
        UPDATE inventory_lots
        SET quantity_remaining = quantity_remaining - %s
        WHERE lot_id = %s AND quantity_remaining >= %s
    """, (quantity_sold, lot_id, quantity_sold))

    if cursor.rowcount == 0:
        # Either the lot doesn't exist, or there wasn't enough left - find out which, for a useful error message.
        cursor.execute("SELECT quantity_remaining FROM inventory_lots WHERE lot_id = %s", (lot_id,))
        row = cursor.fetchone()
        conn.close()
        if row is None:
            return jsonify({"error": "Lot not found"}), 404
        return jsonify({"error": f"Only {row[0]} remaining in this lot"}), 400

    cursor.execute("""
        INSERT INTO sales (lot_id, quantity_sold, sale_price, sale_date, notes)
        VALUES (%s, %s, %s, %s, %s)
    """, (lot_id, quantity_sold, data["sale_price"], data["sale_date"], data.get("notes")))

    conn.commit()
    conn.close()

    return jsonify({"success": True})


@app.route("/api/inventory")
@login_required
def get_inventory():
    """Full inventory list, including sold-out lots, for the dashboard view."""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT
            l.lot_id, l.item_type, l.product_id,
            COALESCE(cards.name, sp.name) AS product_name,
            c.condition_name, l.purchase_price, l.purchase_date,
            l.quantity_purchased, l.quantity_remaining
        FROM inventory_lots l
        LEFT JOIN conditions c ON c.condition_id = l.condition_id
        LEFT JOIN cards ON l.item_type = 'card' AND cards.product_id = l.product_id
        LEFT JOIN sealed_products sp ON l.item_type = 'sealed_product' AND sp.product_id = l.product_id
        ORDER BY l.purchase_date DESC
    """)
    results = cursor.fetchall()
    conn.close()
    return jsonify(results)

@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response


if __name__ == "__main__":
    app.run(port=5000, host="0.0.0.0")
