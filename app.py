import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from flask import Flask, render_template, request


def create_app(db_path=None):
    app = Flask(__name__)
    if db_path is None:
        db_path = Path(app.instance_path) / "reservations.sqlite3"
        db_path.parent.mkdir(exist_ok=True)
    with closing(sqlite3.connect(db_path)) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS reservations (
            id TEXT PRIMARY KEY, request_key TEXT UNIQUE, quantity INTEGER NOT NULL,
            state TEXT NOT NULL, available_after INTEGER NOT NULL
        )""")

    def available(db):
        return db.execute("""SELECT 1 - COALESCE(SUM(quantity), 0)
                             FROM reservations WHERE state = 'active'""").fetchone()[0]

    @app.get("/")
    def home():
        return render_template("index.html")

    @app.get("/api/stock")
    def stock():
        with closing(sqlite3.connect(db_path)) as db:
            return {"available": available(db)}

    @app.post("/api/reservations")
    def reserve():
        data = request.get_json(silent=True)
        quantity = data.get("quantity") if isinstance(data, dict) else None
        if type(quantity) is not int or quantity < 1:
            return {"error": "invalid_quantity"}, 400

        key = request.headers.get("Idempotency-Key") or None
        with closing(sqlite3.connect(db_path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT id, quantity, available_after FROM reservations WHERE request_key = ?",
                               (key,)).fetchone()
            if prior:
                reservation_id, reserved, remaining = prior
                if quantity != reserved:
                    return {"error": "idempotency_conflict"}, 409
                status = 200
            else:
                remaining = available(db)
                if quantity > remaining:
                    return {"error": "insufficient_stock", "available": remaining}, 409
                remaining -= quantity
                reservation_id = uuid4().hex
                db.execute("INSERT INTO reservations VALUES (?, ?, ?, 'active', ?)",
                           (reservation_id, key, quantity, remaining))
                status = 201
        return {"reserved": quantity, "available": remaining}, status, {
            "Location": f"/api/reservations/{reservation_id}"
        }

    @app.route("/api/reservations/<reservation_id>", methods=["GET", "DELETE"])
    def reservation(reservation_id):
        with closing(sqlite3.connect(db_path)) as db, db:
            if request.method == "DELETE":
                db.execute("UPDATE reservations SET state = 'cancelled' WHERE id = ?", (reservation_id,))
            row = db.execute("SELECT quantity, state FROM reservations WHERE id = ?", (reservation_id,)).fetchone()
            if row is None:
                return {"error": "unknown_reservation"}, 404
            return {"id": reservation_id, "quantity": row[0], "state": row[1]}

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5050)
