from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from flask import Flask, jsonify, render_template, request, g, session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
import os
import smtplib
import ssl
import secrets
import time
from email.message import EmailMessage

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"

try:
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH = INSTANCE_DIR / "todos.db"
except OSError:
    TMP_DIR = Path(os.getenv("TMPDIR") or os.getenv("TMP") or "/tmp") / "todo_sqlite"
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH = TMP_DIR / "todos.db"

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False
app.secret_key = os.getenv('FLASK_SECRET', 'dev-secret')


def get_db() -> sqlite3.Connection:
    database = g.get("db")
    if database is None:
        database = sqlite3.connect(DB_PATH)
        database.row_factory = sqlite3.Row
        init_db(database)
        g.db = database
    return database


def close_db(_: object | None = None) -> None:
    database = g.pop("db", None)
    if database is not None:
        database.close()


app.teardown_appcontext(close_db)


def init_db(database: sqlite3.Connection) -> None:
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

    # if existing DB missing email column, add it
    cols = [r[1] for r in database.execute("PRAGMA table_info('users')").fetchall()]
    if 'email' not in cols:
        try:
            database.execute("ALTER TABLE users ADD COLUMN email TEXT")
            database.commit()
        except Exception:
            pass
    # create users table
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    database.commit()

    # ensure a default admin user exists (username: admin, password: admin)
    cur = database.execute("SELECT id FROM users WHERE username = ?", ("admin",))
    if cur.fetchone() is None:
        hashed = generate_password_hash(os.getenv('DEFAULT_ADMIN_PW', 'admin'))
        database.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, 1)", ("admin", hashed))
        database.commit()

    # create timers table for optional shared timer
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS timers (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            duration INTEGER NOT NULL DEFAULT 1500,
            running INTEGER NOT NULL DEFAULT 0,
            end_at INTEGER,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    database.commit()

    # ensure single timer row exists (id = 1)
    cur = database.execute("SELECT id FROM timers WHERE id = 1")
    if cur.fetchone() is None:
        database.execute("INSERT INTO timers (id, duration, running) VALUES (1, 1500, 0)")
        database.commit()
    # create password_resets table
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            expires_at INTEGER NOT NULL,
            used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    database.commit()


def serialize_todo(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "completed": bool(row["completed"]),
        "created_at": row["created_at"],
    }


@app.route("/")
def index() -> str:
    username = None
    is_admin = False
    if session.get('user_id'):
        row = get_db().execute('SELECT username, is_admin FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        if row:
            username = row['username']
            is_admin = bool(row['is_admin'])
    return render_template("index.html", username=username, is_admin=is_admin)


def get_user_by_username(username: str):
    row = get_db().execute("SELECT id, username, password, is_admin FROM users WHERE username = ?", (username,)).fetchone()
    return row


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if not username or not password:
            flash('Nom d\'utilisateur et mot de passe requis')
            return redirect(url_for('login'))

        user = get_user_by_username(username)
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('index'))

        flash('Identifiants invalides')
        return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


def login_required(fn):
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper


@app.route('/admin')
@login_required
def admin():
    db = get_db()
    total = db.execute('SELECT COUNT(*) as cnt FROM todos').fetchone()['cnt']
    users = db.execute('SELECT id, username, is_admin, created_at FROM users ORDER BY id DESC').fetchall()
    return render_template('admin.html', total=total, users=users)


def send_email(to_email: str, subject: str, body_text: str, body_html: str | None = None) -> bool:
    host = os.getenv('SMTP_HOST')
    port = int(os.getenv('SMTP_PORT', '587'))
    user = os.getenv('SMTP_USER')
    password = os.getenv('SMTP_PASS')
    from_addr = os.getenv('EMAIL_FROM', os.getenv('SMTP_USER'))

    if not host or not from_addr:
        return False

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = from_addr
    msg['To'] = to_email
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype='html')

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls(context=context)
            if user and password:
                server.login(user, password)
            server.send_message(msg)
        return True
    except Exception:
        return False


def create_password_reset(db: sqlite3.Connection, user_id: int, expire_seconds: int = 3600) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time() * 1000) + expire_seconds * 1000
    db.execute('INSERT INTO password_resets (user_id, token, expires_at, used) VALUES (?, ?, ?, 0)', (user_id, token, expires_at))
    db.commit()
    return token


def get_password_reset(db: sqlite3.Connection, token: str):
    row = db.execute('SELECT id, user_id, token, expires_at, used FROM password_resets WHERE token = ?', (token,)).fetchone()
    return row


@app.route('/password-reset-request', methods=['GET', 'POST'])
def password_reset_request():
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        if not identifier:
            flash('Veuillez fournir le nom d\'utilisateur ou l\'email')
            return redirect(url_for('password_reset_request'))

        db = get_db()
        user = db.execute('SELECT id, username, email FROM users WHERE username = ? OR email = ?', (identifier, identifier)).fetchone()
        if not user:
            flash('Utilisateur introuvable')
            return redirect(url_for('password_reset_request'))

        if not user['email']:
            flash('Cet utilisateur n\'a pas d\'email enregistré')
            return redirect(url_for('password_reset_request'))

        token = create_password_reset(db, user['id'])
        reset_url = url_for('password_reset', token=token, _external=True)
        text = render_template('password_reset_email.txt', username=user['username'], reset_url=reset_url)
        send_email(user['email'], 'Réinitialisation de votre mot de passe', text)
        flash('Un email de réinitialisation a été envoyé si l\'adresse existe')
        return redirect(url_for('index'))

    return render_template('password_reset_request.html')


@app.route('/password-reset/<token>', methods=['GET', 'POST'])
def password_reset(token):
    db = get_db()
    row = get_password_reset(db, token)
    if not row:
        flash('Token invalide')
        return redirect(url_for('index'))
    if row['used']:
        flash('Ce lien a déjà été utilisé')
        return redirect(url_for('index'))
    if int(row['expires_at']) < int(time.time() * 1000):
        flash('Le lien a expiré')
        return redirect(url_for('index'))

    if request.method == 'POST':
        pw = request.form.get('password', '').strip()
        pw2 = request.form.get('password2', '').strip()
        if not pw or pw != pw2:
            flash('Les mots de passe doivent correspondre et ne pas être vides')
            return redirect(url_for('password_reset', token=token))
        hashed = generate_password_hash(pw)
        db.execute('UPDATE users SET password = ? WHERE id = ?', (hashed, row['user_id']))
        db.execute('UPDATE password_resets SET used = 1 WHERE id = ?', (row['id'],))
        db.commit()
        flash('Mot de passe mis à jour; vous pouvez maintenant vous connecter')
        return redirect(url_for('login'))

    return render_template('password_reset_form.html', token=token)


@app.route('/admin/send-reset/<int:user_id>', methods=['POST'])
@login_required
def admin_send_reset(user_id: int):
    # only admins can trigger
    cur = get_db().execute('SELECT is_admin FROM users WHERE id = ?', (session.get('user_id'),)).fetchone()
    if not cur or not cur['is_admin']:
        flash('Accès refusé')
        return redirect(url_for('admin'))

    db = get_db()
    user = db.execute('SELECT id, username, email FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        flash('Utilisateur introuvable')
        return redirect(url_for('admin'))
    if not user['email']:
        flash('L\'utilisateur n\'a pas d\'email')
        return redirect(url_for('admin'))

    token = create_password_reset(db, user['id'])
    reset_url = url_for('password_reset', token=token, _external=True)
    text = render_template('password_reset_email.txt', username=user['username'], reset_url=reset_url)
    ok = send_email(user['email'], 'Réinitialisation de votre mot de passe', text)
    if ok:
        flash('Email envoyé')
    else:
        flash('Échec envoi email; vérifiez la configuration SMTP')
    return redirect(url_for('admin'))


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


def read_timer_row(database: sqlite3.Connection):
    row = database.execute("SELECT duration, running, end_at FROM timers WHERE id = 1").fetchone()
    if row is None:
        return {"duration": 1500, "running": False, "end_at": None}
    return {"duration": row["duration"], "running": bool(row["running"]), "end_at": row["end_at"]}


@app.route('/api/timer', methods=['GET'])
def get_timer():
    db = get_db()
    t = read_timer_row(db)
    now = int(round(__import__('time').time() * 1000))
    remaining = None
    if t['running'] and t['end_at']:
        remaining = max(0, int((t['end_at'] - now) / 1000))
    else:
        remaining = t['duration']
    return jsonify({"duration": t['duration'], "running": t['running'], "end_at": t['end_at'], "remaining": remaining}), 200


@app.route('/api/timer/start', methods=['POST'])
def start_timer():
    payload = request.get_json(silent=True) or {}
    duration = int(payload.get('duration', 1500))
    now = int(round(__import__('time').time() * 1000))
    end_at = now + duration * 1000
    db = get_db()
    db.execute('UPDATE timers SET duration = ?, running = 1, end_at = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1', (duration, end_at))
    db.commit()
    return get_timer()


@app.route('/api/timer/pause', methods=['POST'])
def pause_timer():
    db = get_db()
    row = read_timer_row(db)
    now = int(round(__import__('time').time() * 1000))
    remaining = row['duration']
    if row['running'] and row['end_at']:
        remaining = max(0, int((row['end_at'] - now) / 1000))
    # store remaining as new duration and stop
    db.execute('UPDATE timers SET duration = ?, running = 0, end_at = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = 1', (remaining,))
    db.commit()
    return get_timer()


@app.route('/api/timer/reset', methods=['POST'])
def reset_timer():
    db = get_db()
    default = int(request.get_json(silent=True) or {}).get('duration', 1500)
    db.execute('UPDATE timers SET duration = ?, running = 0, end_at = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = 1', (default,))
    db.commit()
    return get_timer()


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
