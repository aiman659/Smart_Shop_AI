from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "smart_shop.db"


class DatabaseManager:
    """Single SQLite access layer used by every Smart Shop page."""

    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()
        self._create_schema()

    def _create_schema(self) -> None:
        self.cursor.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                interests TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS products (
                product_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                brand TEXT DEFAULT '',
                price REAL NOT NULL DEFAULT 0,
                stock INTEGER NOT NULL DEFAULT 0,
                rating REAL NOT NULL DEFAULT 0,
                sales INTEGER NOT NULL DEFAULT 0,
                supplier TEXT DEFAULT '',
                links TEXT DEFAULT '',
                content TEXT DEFAULT '',
                description TEXT DEFAULT '',
                image TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_products_category
                ON products(category);

            CREATE INDEX IF NOT EXISTS idx_products_name
                ON products(name);

            CREATE INDEX IF NOT EXISTS idx_products_sales
                ON products(sales);
            """
        )
        self.connection.commit()

    def close(self) -> None:
        try:
            self.connection.close()
        except Exception:
            pass

    # ---------- users ----------
    def register_user(self, username: str, password: str, interests: str = "") -> bool:
        try:
            self.cursor.execute(
                "INSERT INTO users(username,password,interests) VALUES(?,?,?)",
                (username, password, interests),
            )
            self.connection.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def login_user(self, username: str, password: str):
        return self.cursor.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, password),
        ).fetchone()

    def total_users(self) -> int:
        return int(self.cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    # ---------- products ----------
    def add_product(
        self,
        name,
        category,
        brand="",
        price=0,
        stock=0,
        rating=0,
        sales=0,
        supplier="",
        links="",
        content="",
        description="",
        image="",
    ):
        self.cursor.execute(
            """
            INSERT INTO products
            (name,category,brand,price,stock,rating,sales,supplier,links,content,description,image)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                name, category, brand, float(price or 0), int(stock or 0),
                float(rating or 0), int(sales or 0), supplier, links,
                content, description, image,
            ),
        )
        self.connection.commit()
        return self.cursor.lastrowid

    def update_product(
        self,
        product_id,
        name,
        category,
        brand,
        price,
        stock,
        rating,
        sales,
        supplier,
        links,
        content,
        description,
        image,
    ):
        self.cursor.execute(
            """
            UPDATE products SET
                name=?, category=?, brand=?, price=?, stock=?, rating=?,
                sales=?, supplier=?, links=?, content=?, description=?, image=?
            WHERE product_id=?
            """,
            (
                name, category, brand, float(price or 0), int(stock or 0),
                float(rating or 0), int(sales or 0), supplier, links,
                content, description, image, product_id,
            ),
        )
        self.connection.commit()

    def delete_product(self, product_id) -> None:
        self.cursor.execute("DELETE FROM products WHERE product_id=?", (product_id,))
        self.connection.commit()

    def get_product(self, product_id):
        return self.cursor.execute(
            "SELECT * FROM products WHERE product_id=?", (product_id,)
        ).fetchone()

    def get_all_products(self):
        return self.cursor.execute(
            "SELECT * FROM products ORDER BY sales DESC, product_id DESC"
        ).fetchall()

    def latest_products(self, limit: int = 8):
        return self.cursor.execute(
            "SELECT * FROM products ORDER BY product_id DESC LIMIT ?", (limit,)
        ).fetchall()

    def best_selling_products(self, limit: int = 8):
        return self.cursor.execute(
            "SELECT * FROM products ORDER BY sales DESC, rating DESC LIMIT ?", (limit,)
        ).fetchall()

    def search_and_filter(self, keyword: str = "", category: str = "All", sort: str = "featured"):
        clauses = []
        params = []

        if keyword:
            like = f"%{keyword}%"
            clauses.append(
                "(name LIKE ? OR brand LIKE ? OR supplier LIKE ? OR category LIKE ? OR description LIKE ?)"
            )
            params.extend([like, like, like, like, like])

        if category and category != "All":
            clauses.append("category = ?")
            params.append(category)

        where = " WHERE " + " AND ".join(clauses) if clauses else ""

        order_map = {
            "featured": "sales DESC, rating DESC, product_id DESC",
            "price_low": "price ASC, product_id DESC",
            "price_high": "price DESC, product_id DESC",
            "rating": "rating DESC, sales DESC",
            "newest": "product_id DESC",
            "stock": "stock DESC, sales DESC",
        }
        order = order_map.get(sort, order_map["featured"])

        return self.cursor.execute(
            f"SELECT * FROM products{where} ORDER BY {order}",
            params,
        ).fetchall()

    def get_categories(self):
        rows = self.cursor.execute(
            """
            SELECT category, COUNT(*) AS product_count, COALESCE(SUM(sales),0) AS sales,
                   COALESCE(SUM(stock),0) AS stock
            FROM products
            GROUP BY category
            ORDER BY category COLLATE NOCASE
            """
        ).fetchall()
        return [row["category"] for row in rows]

    def category_stats(self):
        return self.cursor.execute(
            """
            SELECT category,
                   COUNT(*) AS product_count,
                   COALESCE(SUM(sales),0) AS sales,
                   COALESCE(SUM(stock),0) AS stock,
                   ROUND(AVG(rating),1) AS rating,
                   ROUND(SUM(price * stock),2) AS inventory_value
            FROM products
            GROUP BY category
            ORDER BY sales DESC, category COLLATE NOCASE
            """
        ).fetchall()

    def total_products(self) -> int:
        return int(self.cursor.execute("SELECT COUNT(*) FROM products").fetchone()[0])

    def total_categories(self) -> int:
        return int(self.cursor.execute("SELECT COUNT(DISTINCT category) FROM products").fetchone()[0])

    def total_stock(self) -> int:
        return int(self.cursor.execute("SELECT COALESCE(SUM(stock),0) FROM products").fetchone()[0])

    def total_sales(self) -> int:
        return int(self.cursor.execute("SELECT COALESCE(SUM(sales),0) FROM products").fetchone()[0])

    def inventory_value(self) -> float:
        return float(self.cursor.execute(
            "SELECT COALESCE(SUM(price * stock),0) FROM products"
        ).fetchone()[0])

    def estimated_revenue(self) -> float:
        return float(self.cursor.execute(
            "SELECT COALESCE(SUM(price * sales),0) FROM products"
        ).fetchone()[0])

    def average_rating(self) -> float:
        return float(self.cursor.execute(
            "SELECT COALESCE(AVG(rating),0) FROM products"
        ).fetchone()[0])

    def low_stock_products(self, threshold: int = 12, limit: int = 8):
        return self.cursor.execute(
            """
            SELECT * FROM products
            WHERE stock <= ?
            ORDER BY stock ASC, sales DESC
            LIMIT ?
            """,
            (threshold, limit),
        ).fetchall()

    def top_rated_products(self, limit: int = 8):
        return self.cursor.execute(
            "SELECT * FROM products ORDER BY rating DESC, sales DESC LIMIT ?", (limit,)
        ).fetchall()

    def analytics_summary(self):
        return {
            "total_products": self.total_products(),
            "total_users": self.total_users(),
            "total_categories": self.total_categories(),
            "total_stock": self.total_stock(),
            "total_sales": self.total_sales(),
            "inventory_value": self.inventory_value(),
            "estimated_revenue": self.estimated_revenue(),
            "average_rating": self.average_rating(),
        }

    def clear_products(self):
        self.cursor.execute("DELETE FROM products")
        try:
            self.cursor.execute("DELETE FROM sqlite_sequence WHERE name='products'")
        except sqlite3.OperationalError:
            pass
        self.connection.commit()
