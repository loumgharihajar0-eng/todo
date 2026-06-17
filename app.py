from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import Flask, jsonify, render_template, request, g

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
DB_PATH = INSTANCE_DIR / "todos.db"

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False


def get_db() -> sqlite3.Connection:
    database = g.get("db")
    if database is None:
        INSTANCE_DIR.mkdir(exist_ok=True)
        database = sqlite3.connect(DB_PATH)
        database.row_factory = sqlite3.Row
        g.db = database
    return database


def close_db(_: object | None = None) -> None:
    database = g.pop("db", None)
    if database is not None:
        database.close()


app.teardown_appcontext(close_db)


def init_db() -> None:
    database = sqlite3.connect(DB_PATH)
    try:
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        database.commit()
    finally:
        database.close()


def serialize_todo(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "completed": bool(row["completed"]),
        "created_at": row["created_at"],
    }


with app.app_context():
    init_db()


@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/api/todos", methods=["GET"])
def list_todos() -> tuple[object, int]:
    rows = get_db().execute(
        "SELECT id, title, completed, created_at FROM todos ORDER BY id DESC"
    ).fetchall()
    return jsonify([serialize_todo(row) for row in rows]), 200


@app.route("/api/todos", methods=["POST"])
def create_todo() -> tuple[object, int]:
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title", "")).strip()

    if not title:
        return jsonify({"error": "Le titre est obligatoire."}), 400

    cursor = get_db().execute(
        "INSERT INTO todos (title, completed) VALUES (?, 0)",
        (title,),
    )
    get_db().commit()

    row = get_db().execute(
        "SELECT id, title, completed, created_at FROM todos WHERE id = ?",
        (cursor.lastrowid,),
    ).fetchone()
    return jsonify(serialize_todo(row)), 201


@app.route("/api/todos/<int:todo_id>", methods=["PATCH"])
def update_todo(todo_id: int) -> tuple[object, int]:
    payload = request.get_json(silent=True) or {}
    fields: list[str] = []
    values: list[object] = []

    if "title" in payload:
        title = str(payload.get("title", "")).strip()
        if not title:
            return jsonify({"error": "Le titre ne peut pas être vide."}), 400
        fields.append("title = ?")
        values.append(title)

    if "completed" in payload:
        fields.append("completed = ?")
        values.append(1 if bool(payload.get("completed")) else 0)

    if not fields:
        return jsonify({"error": "Aucune donnée à mettre à jour."}), 400

    values.append(todo_id)
    database = get_db()
    result = database.execute(
        f"UPDATE todos SET {', '.join(fields)} WHERE id = ?",
        values,
    )
    database.commit()

    if result.rowcount == 0:
        return jsonify({"error": "Todo introuvable."}), 404

    row = database.execute(
        "SELECT id, title, completed, created_at FROM todos WHERE id = ?",
        (todo_id,),
    ).fetchone()
    return jsonify(serialize_todo(row)), 200


@app.route("/api/todos/<int:todo_id>", methods=["DELETE"])
def delete_todo(todo_id: int) -> tuple[object, int]:
    result = get_db().execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    get_db().commit()

    if result.rowcount == 0:
        return jsonify({"error": "Todo introuvable."}), 404

    return jsonify({"ok": True}), 200


@app.route("/api/health", methods=["GET"])
def health() -> tuple[object, int]:
    return jsonify({"ok": True}), 200


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
