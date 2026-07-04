"""セッション認証(HttpOnly Cookie + トークン)と権限デコレータ。"""
import functools
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db, transaction
from .permissions import permissions_for

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

SESSION_COOKIE = "lul_session"
SESSION_DAYS = 30


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _load_user_from_request():
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    db = get_db()
    row = db.execute(
        """SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id
           WHERE s.token_hash = ? AND s.expires_at > datetime('now')""",
        (_hash_token(token),),
    ).fetchone()
    return row


def current_user():
    if "user" not in g:
        g.user = _load_user_from_request()
    return g.user


def user_permissions(user) -> list[str]:
    db = get_db()
    granted = [
        r["permission"]
        for r in db.execute(
            "SELECT permission FROM user_permissions WHERE user_id = ?", (user["id"],)
        ).fetchall()
    ]
    return permissions_for(user["exp"], user["role"], granted)


def login_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if current_user() is None:
            return jsonify(error="ログインが必要です"), 401
        return view(**kwargs)
    return wrapped


def permission_required(perm: str):
    def decorator(view):
        @functools.wraps(view)
        def wrapped(**kwargs):
            user = current_user()
            if user is None:
                return jsonify(error="ログインが必要です"), 401
            if perm not in user_permissions(user):
                return jsonify(error=f"この操作には権限が必要です: {perm}"), 403
            return view(**kwargs)
        return wrapped
    return decorator


def admin_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        user = current_user()
        if user is None:
            return jsonify(error="ログインが必要です"), 401
        if user["role"] != "admin":
            return jsonify(error="管理者権限が必要です"), 403
        return view(**kwargs)
    return wrapped


def _issue_session(resp, user_id: int):
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    db = get_db()
    with transaction(db):
        db.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (_hash_token(token), user_id, expires.strftime("%Y-%m-%d %H:%M:%S")),
        )
        db.execute("DELETE FROM sessions WHERE expires_at <= datetime('now')")
    resp.set_cookie(
        SESSION_COOKIE, token,
        max_age=SESSION_DAYS * 86400,
        httponly=True, samesite="Lax", path="/",
        secure=request.is_secure or current_app.config["COOKIE_SECURE"],
    )
    return resp


@bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    password = data.get("password") or ""
    if not name or len(name) > 20:
        return jsonify(error="表示名は1〜20文字で入力してください"), 400
    if len(password) < 8:
        return jsonify(error="パスワードは8文字以上にしてください"), 400
    db = get_db()
    if db.execute("SELECT 1 FROM users WHERE name = ?", (name,)).fetchone():
        return jsonify(error="その表示名は既に使われています"), 409
    cur = db.execute(
        "INSERT INTO users (name, password_hash) VALUES (?, ?)",
        (name, generate_password_hash(password)),
    )
    return _issue_session(jsonify(ok=True, name=name), cur.lastrowid)


@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    password = data.get("password") or ""
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE name = ?", (name,)).fetchone()
    if user is None or not check_password_hash(user["password_hash"], password):
        return jsonify(error="表示名またはパスワードが違います"), 401
    return _issue_session(jsonify(ok=True, name=user["name"]), user["id"])


@bp.post("/password")
def change_password():
    user = current_user()
    if user is None:
        return jsonify(error="ログインが必要です"), 401
    data = request.get_json(silent=True) or {}
    current = data.get("current_password") or ""
    new = data.get("new_password") or ""
    if not check_password_hash(user["password_hash"], current):
        return jsonify(error="現在のパスワードが違います"), 403
    if len(new) < 8:
        return jsonify(error="新しいパスワードは8文字以上にしてください"), 400
    db = get_db()
    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(new), user["id"]),
    )
    return jsonify(ok=True)


@bp.patch("/profile")
def rename():
    user = current_user()
    if user is None:
        return jsonify(error="ログインが必要です"), 401
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name or len(name) > 20:
        return jsonify(error="表示名は1〜20文字で入力してください"), 400
    db = get_db()
    if db.execute("SELECT 1 FROM users WHERE name = ? AND id != ?", (name, user["id"])).fetchone():
        return jsonify(error="その表示名は既に使われています"), 409
    db.execute("UPDATE users SET name = ? WHERE id = ?", (name, user["id"]))
    return jsonify(ok=True, name=name)


@bp.post("/logout")
def logout():
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db = get_db()
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))
    resp = jsonify(ok=True)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp
