from __future__ import annotations

from pathlib import Path
import sys
import re
from math import ceil

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from database.database import DatabaseManager

app = Flask(__name__, template_folder=str(BASE_DIR / "templates"), static_folder=str(BASE_DIR / "static"))
app.secret_key = "smart-shop-ai-development-key-2026"


def ensure_catalogue():
    db = DatabaseManager()
    try:
        empty = db.total_products() == 0
    finally:
        db.close()
    if empty:
        from seed_shop import seed_catalogue
        seed_catalogue()


def cart_map():
    raw = session.get("cart", {})
    if isinstance(raw, dict):
        clean = {}
        for key, value in raw.items():
            try:
                pid, qty = int(key), max(1, int(value))
                clean[pid] = qty
            except (TypeError, ValueError):
                continue
        return clean
    if isinstance(raw, list):
        result = {}
        for pid in raw:
            try:
                pid = int(pid)
                result[pid] = result.get(pid, 0) + 1
            except (TypeError, ValueError):
                pass
        return result
    return {}


def wishlist_ids():
    raw = session.get("wishlist", [])
    if not isinstance(raw, list):
        return []
    result = []
    for value in raw:
        try:
            pid = int(value)
            if pid not in result:
                result.append(pid)
        except (TypeError, ValueError):
            pass
    return result


def ai_score(product):
    sales = int(product["sales"] or 0)
    rating = float(product["rating"] or 0)
    stock = int(product["stock"] or 0)
    sales_component = min(sales / 420, 1) * 45
    rating_component = min(rating / 5, 1) * 30
    availability_component = min(stock / 85, 1) * 25
    return round(sales_component + rating_component + availability_component)


app.jinja_env.globals["ai_score"] = ai_score
app.jinja_env.globals["wishlist_ids"] = wishlist_ids


def paginate(items, page, per_page=12):
    total = len(items)
    pages = max(1, ceil(total / per_page))
    page = min(max(1, page), pages)
    start = (page - 1) * per_page
    return items[start:start + per_page], page, pages, total


@app.context_processor
def global_shop_data():
    cart = cart_map()
    wish = wishlist_ids()
    return {
        "cart_count": sum(cart.values()),
        "cart_map": cart,
        "wishlist_count": len(wish),
        "wishlist_ids": wish,
        "current_endpoint": request.endpoint or "",
        "ai_score": ai_score,
    }


@app.before_request
def startup():
    if not getattr(app, "_catalogue_ready", False):
        ensure_catalogue()
        app._catalogue_ready = True


@app.route("/")
def home():
    db = DatabaseManager()
    try:
        best_products = db.best_selling_products(8)
        latest_products = db.latest_products(8)
        categories_raw = db.category_stats()
        all_products = db.get_all_products()
        summary = db.analytics_summary()
    finally:
        db.close()
    first_image = {}
    for p in all_products:
        first_image.setdefault(p["category"], p["image"] or "product_1.svg")
    categories = [dict(c) | {"image": first_image.get(c["category"], "product_1.svg")} for c in categories_raw]
    return render_template("index.html", best_products=best_products, latest_products=latest_products,
                           categories=categories, summary=summary)


@app.route("/products")
def products():
    keyword = request.args.get("search", "").strip()
    category = request.args.get("category", "All").strip() or "All"
    sort = request.args.get("sort", "featured").strip()
    try: page = int(request.args.get("page", 1))
    except ValueError: page = 1
    db = DatabaseManager()
    try:
        all_items = list(db.search_and_filter(keyword, category, sort))
        categories = db.get_categories()
    finally:
        db.close()
    items, page, pages, total = paginate(all_items, page, 12)
    return render_template("products.html", products=items, categories=categories, keyword=keyword,
                           selected_category=category, selected_sort=sort, page=page, pages=pages, total=total)


@app.route("/search")
def search():
    keyword = request.args.get("q", "").strip()
    category = request.args.get("category", "All").strip() or "All"
    sort = request.args.get("sort", "featured").strip()
    try: page = int(request.args.get("page", 1))
    except ValueError: page = 1
    db = DatabaseManager()
    try:
        all_items = list(db.search_and_filter(keyword, category, sort))
        categories = db.get_categories()
    finally:
        db.close()
    items, page, pages, total = paginate(all_items, page, 12)
    return render_template("search.html", products=items, categories=categories, keyword=keyword,
                           selected_category=category, selected_sort=sort, page=page, pages=pages, total=total)


@app.route("/product/<int:product_id>")
def product_detail(product_id):
    db = DatabaseManager()
    try:
        product = db.get_product(product_id)
        related = []
        if product:
            related = [p for p in db.search_and_filter("", product["category"], "featured") if p["product_id"] != product_id][:4]
    finally:
        db.close()
    if not product:
        return render_template("404.html"), 404
    return render_template("product_detail.html", product=product, related=related)


@app.route("/products/add", methods=["GET", "POST"])
def add_product():
    db = DatabaseManager()
    try:
        categories = db.get_categories()
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            category = request.form.get("category", "").strip()
            brand = request.form.get("brand", "").strip() or "NovaWear"
            supplier = request.form.get("supplier", "").strip() or "FashionHub Supply"
            description = request.form.get("description", "").strip()
            image = request.form.get("image", "").strip() or "product_1.svg"
            links = request.form.get("links", "").strip()
            if not name or not category:
                flash("Product name and category are required.")
                return render_template("add_product.html", categories=categories, product=None, edit_mode=False)
            def number(name, kind=float, default=0):
                try: return max(0, kind(request.form.get(name, default)))
                except (TypeError, ValueError): return default
            price = number("price", float); stock = number("stock", int); sales = number("sales", int)
            rating = min(5, number("rating", float))
            db.add_product(name, category, brand, price, stock, rating, sales, supplier,
                           links, description, description, image)
            flash("Product added successfully.")
            return redirect(url_for("products"))
    finally:
        db.close()
    return render_template("add_product.html", categories=categories, product=None, edit_mode=False)


@app.route("/products/edit/<int:product_id>", methods=["GET", "POST"])
def edit_product(product_id):
    db = DatabaseManager()
    try:
        product = db.get_product(product_id)
        categories = db.get_categories()
        if not product:
            return render_template("404.html"), 404
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            category = request.form.get("category", "").strip()
            brand = request.form.get("brand", "").strip()
            supplier = request.form.get("supplier", "").strip()
            description = request.form.get("description", "").strip()
            image = request.form.get("image", "").strip() or product["image"]
            links = request.form.get("links", "").strip()
            def number(name, kind=float, default=0):
                try: return max(0, kind(request.form.get(name, default)))
                except (TypeError, ValueError): return default
            price = number("price", float); stock = number("stock", int); sales = number("sales", int)
            rating = min(5, number("rating", float))
            db.update_product(product_id, name, category, brand, price, stock, rating, sales,
                              supplier, links, description, description, image)
            flash("Product updated successfully.")
            return redirect(url_for("product_detail", product_id=product_id))
    finally:
        db.close()
    return render_template("add_product.html", categories=categories, product=product, edit_mode=True)


@app.route("/products/delete/<int:product_id>", methods=["POST"])
def delete_product(product_id):
    db = DatabaseManager()
    try: db.delete_product(product_id)
    finally: db.close()
    cart = cart_map(); cart.pop(product_id, None); session["cart"] = cart
    wish = wishlist_ids(); session["wishlist"] = [x for x in wish if x != product_id]
    flash("Product deleted.")
    return redirect(url_for("products"))


@app.route("/dashboard")
def dashboard():
    db = DatabaseManager()
    try:
        summary = db.analytics_summary()
        best_products = db.best_selling_products(6)
        latest_products = db.latest_products(6)
        top_categories = db.category_stats()[:8]
        low_stock = db.low_stock_products(12, 6)
    finally: db.close()
    return render_template("dashboard.html", summary=summary, best_products=best_products,
                           latest_products=latest_products, top_categories=top_categories, low_stock=low_stock)


@app.route("/analytics")
def analytics():
    db = DatabaseManager()
    try:
        summary = db.analytics_summary()
        category_stats = db.category_stats()
        best_products = db.best_selling_products(10)
        low_stock = db.low_stock_products(12, 8)
        top_rated = db.top_rated_products(6)
    finally: db.close()
    max_sales = max([int(x["sales"]) for x in category_stats] or [1])
    return render_template("analytics.html", summary=summary, category_stats=category_stats,
                           best_products=best_products, low_stock=low_stock, top_rated=top_rated,
                           max_sales=max_sales)


@app.route("/recommendations")
def recommendations():
    db = DatabaseManager()
    try: products = db.get_all_products()
    finally: db.close()
    rows = []
    for p in products:
        score = ai_score(p)
        sales, rating, stock = int(p["sales"] or 0), float(p["rating"] or 0), int(p["stock"] or 0)
        if sales >= 300 and rating >= 4.5: reason = "Strong sales and customer ratings."
        elif stock <= 15: reason = "Good demand signal; stock needs attention."
        elif rating >= 4.8: reason = "Excellent customer rating."
        elif sales >= 250: reason = "Above-average sales velocity."
        else: reason = "Balanced sales, rating and availability."
        rows.append({"product": p, "score": score, "reason": reason})
    rows.sort(key=lambda x: x["score"], reverse=True)
    return render_template("recommendations.html", recommendations=rows[:12])


@app.route("/cart")
def cart():
    cart = cart_map(); rows = []
    db = DatabaseManager()
    try:
        for product_id, quantity in cart.items():
            product = db.get_product(product_id)
            if product: rows.append({"product": product, "quantity": quantity})
    finally: db.close()
    subtotal = sum(float(item["product"]["price"]) * item["quantity"] for item in rows)
    return render_template("cart.html", items=rows, subtotal=subtotal)


@app.route("/cart/add/<int:product_id>", methods=["POST", "GET"])
def add_to_cart(product_id):
    db = DatabaseManager()
    try: product = db.get_product(product_id)
    finally: db.close()
    if not product:
        flash("Product not found."); return redirect(url_for("products"))
    if int(product["stock"]) <= 0:
        flash("That product is currently out of stock."); return redirect(request.referrer or url_for("products"))
    cart = cart_map(); current = cart.get(product_id, 0)
    if current < int(product["stock"]):
        cart[product_id] = current + 1; session["cart"] = cart
        flash(f"{product['name']} added to cart.")
    else: flash("Maximum available stock is already in your cart.")
    return redirect(request.referrer or url_for("products"))


@app.route("/cart/update/<int:product_id>", methods=["POST"])
def update_cart(product_id):
    db = DatabaseManager()
    try: product = db.get_product(product_id)
    finally: db.close()
    cart = cart_map()
    try: quantity = int(request.form.get("quantity", 1))
    except ValueError: quantity = 1
    if not product or quantity <= 0: cart.pop(product_id, None)
    else: cart[product_id] = min(quantity, int(product["stock"]))
    session["cart"] = cart
    flash("Cart updated.")
    return redirect(url_for("cart"))


@app.route("/cart/remove/<int:product_id>", methods=["POST"])
def remove_from_cart(product_id):
    cart = cart_map(); cart.pop(product_id, None); session["cart"] = cart
    flash("Item removed from cart.")
    return redirect(url_for("cart"))


@app.route("/cart/clear", methods=["POST"])
def clear_cart():
    session["cart"] = {}; flash("Cart cleared."); return redirect(url_for("cart"))


@app.route("/wishlist")
def wishlist():
    ids = wishlist_ids(); products = []
    db = DatabaseManager()
    try:
        for pid in ids:
            p = db.get_product(pid)
            if p: products.append(p)
    finally: db.close()
    return render_template("wishlist.html", products=products)


@app.route("/wishlist/toggle/<int:product_id>", methods=["POST", "GET"])
def toggle_wishlist(product_id):
    db = DatabaseManager()
    try: product = db.get_product(product_id)
    finally: db.close()
    if not product:
        flash("Product not found."); return redirect(url_for("products"))
    ids = wishlist_ids()
    if product_id in ids:
        ids.remove(product_id); flash("Removed from wishlist.")
    else:
        ids.append(product_id); flash("Added to wishlist.")
    session["wishlist"] = ids
    return redirect(request.referrer or url_for("wishlist"))


@app.route("/support")
def support():
    return render_template("support.html")

@app.route("/api/support", methods=["POST"])
def support_api():
    """Small backend-connected FAQ assistant; uses the live catalogue without adding DB tables."""
    payload = request.get_json(silent=True) or {}
    question = str(payload.get("question", "")).strip()
    q = question.lower()
    if not question:
        return jsonify({"answer": "Please type a question.", "products": []})
    products = []
    db = DatabaseManager()
    try:
        if any(word in q for word in ("product", "stock", "price", "shirt", "shoe", "dress", "phone", "laptop")):
            keyword = next((w for w in re.findall(r"[a-z0-9]+", q) if len(w) >= 4 and w not in {"product","stock","price","tell","about","what","show","please"}), "")
            if keyword:
                products = [dict(p) for p in db.search_and_filter(keyword, "All", "featured")[:3]]
            if products:
                names = ", ".join(p["name"] for p in products)
                answer = f"I found these catalogue matches: {names}. Open Products for full price, rating and stock details."
            else:
                answer = "Use Products or Smart Search to see live product names, prices, ratings, brands and stock from the connected catalogue."
        elif "track" in q or "order" in q:
            answer = "Order tracking is a demo because this project does not have an orders table or live courier integration."
        elif "ship" in q:
            answer = "Shipping is currently informational only; no live courier or shipping API is connected in this local project."
        elif "pay" in q or "payment" in q:
            answer = "Checkout is demo-safe: no real payment is processed and no payment gateway is connected."
        elif "return" in q or "refund" in q:
            answer = "Returns and refunds are policy guidance only in this version; there is no refund-processing backend."
        else:
            answer = "I can help with product information, order-tracking demos, shipping, payments, returns and refunds."
    finally:
        db.close()
    return jsonify({"answer": answer, "products": [{"product_id": p["product_id"], "name": p["name"], "price": p["price"], "stock": p["stock"]} for p in products]})



@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip(); password = request.form.get("password", "").strip()
        if not username or not password:
            flash("Username and password are required."); return redirect(url_for("login"))
        db = DatabaseManager()
        try: user = db.login_user(username, password)
        finally: db.close()
        if user:
            session["user_id"] = user["user_id"]; session["username"] = user["username"]
            flash("Welcome back!"); return redirect(url_for("dashboard"))
        flash("Invalid username or password.")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip(); password = request.form.get("password", "").strip()
        interests = request.form.get("interests", "").strip()
        if not username or not password:
            flash("Username and password are required."); return redirect(url_for("register"))
        db = DatabaseManager()
        try: success = db.register_user(username, password, interests)
        finally: db.close()
        if success:
            flash("Account created. You can now sign in."); return redirect(url_for("login"))
        flash("That username already exists.")
    return render_template("register.html")


@app.route("/logout")
def logout():
    session.pop("user_id", None); session.pop("username", None)
    flash("You have been logged out."); return redirect(url_for("home"))


@app.route("/about")
def about(): return render_template("about.html")

@app.route("/contact")
def contact(): return render_template("contact.html")

@app.errorhandler(404)
def not_found(error): return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(error): return render_template("500.html"), 500


if __name__ == "__main__":
    print("\n==============================================")
    print("          SMART SHOP AI")
    print("==============================================")
    print("Open: http://127.0.0.1:5000\n")
    app.run(host="127.0.0.1", port=5000, debug=True)
