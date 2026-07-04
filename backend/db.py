"""SQLite 接続管理・初期化・シードデータ。"""
import os
import sqlite3
from contextlib import contextmanager

from flask import current_app, g
from werkzeug.security import generate_password_hash

SEED_QUESTS = [
    # (id, title, description, exp, pts, category, cooldown_hours)  cooldown NULL = 1回限り
    ("q_use_tool",       "新ツールを1回使う",       "自作ツールを実際に触って動作を確認する",                 30,  10, "usage",    24),
    ("q_workshop",       "勉強会に参加する",         "月次の社内勉強会にオンライン/オフラインで参加",           80,  25, "usage",    600),
    ("q_read_doc",       "資料を読了する",           "公開されている学習資料を最後まで読む",                   40,  12, "learning", 24),
    ("q_quiz",           "理解度クイズに合格",       "資料に付属するミニクイズをクリア",                       60,  15, "learning", None),
    ("q_share",          "他のメンバーに紹介する",   "ツールや資料を同僚に共有し使ってもらう",                 70,  20, "usage",    None),
    ("q_kaizen_report",  "改善の効果を報告する",     "実施した改善のBefore/After・効果を共有する",             150, 50, "kaizen",   168),
    ("q_kaizen_practice","他人の改善提案に乗って実践", "誰かの改善アイデアを自分の業務にも適用して報告",         90,  30, "kaizen",   168),
]

SEED_SHOP = [
    # (id, title, description, cost, effect, repeatable)
    ("s_advanced",  "上級編ツールを解放",        "応用ケースを扱う上位バージョンにアクセス",             40,  None,                        0),
    ("s_seat",      "勉強会 優先予約枠",         "次回勉強会の座席を先取り予約できる",                   30,  None,                        1),
    ("s_qa",        "個別質問タイム(15分)",     "作者に直接質問・相談できる枠を確保",                   60,  None,                        1),
    ("s_case",      "限定ケーススタディ資料",    "社外未公開の実践事例資料を解放",                       50,  None,                        0),
    ("s_boost",     "XPブースター ×5",           "次の5クエストの獲得EXPが1.5倍(シルバー以上で購入可)", 80,  "boost5",                    1),
    ("s_approver",  "承認者権限を先行解放",      "ゴールド到達を待たずに改善提案の承認権限を獲得",       150, "grant:approve_proposals",   0),
]


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        # isolation_level=None: 自動コミットにして、複数文の書き込みは
        # transaction() で明示的に BEGIN IMMEDIATE する
        g.db = sqlite3.connect(current_app.config["DATABASE"], isolation_level=None)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA busy_timeout = 5000")
    return g.db


@contextmanager
def transaction(db: sqlite3.Connection):
    """書き込みトランザクション。

    BEGIN IMMEDIATE で書き込みロックを先取りし、check-then-act 型の
    競合(ポイント二重消費・クエスト二重完了など)を直列化して防ぐ。
    """
    db.execute("BEGIN IMMEDIATE")
    try:
        yield
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app):
    os.makedirs(os.path.dirname(app.config["DATABASE"]), exist_ok=True)
    db = sqlite3.connect(app.config["DATABASE"])
    db.row_factory = sqlite3.Row
    try:
        with app.open_resource("schema.sql") as f:
            db.executescript(f.read().decode("utf8"))
        migrate(db)
        seed(db, admin_password=app.config["ADMIN_PASSWORD"])
        db.commit()
    finally:
        db.close()


def migrate(db: sqlite3.Connection):
    """既存DB向けの後方互換マイグレーション(schema.sql は IF NOT EXISTS のため列追加はここで行う)。"""
    cols = [r["name"] for r in db.execute("PRAGMA table_info(quests)").fetchall()]
    if "content_id" not in cols:
        db.execute("ALTER TABLE quests ADD COLUMN content_id INTEGER REFERENCES contents(id)")


def seed(db: sqlite3.Connection, admin_password: str):
    for row in SEED_QUESTS:
        db.execute(
            """INSERT OR IGNORE INTO quests (id, title, description, exp, pts, category, cooldown_hours)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            row,
        )
    for row in SEED_SHOP:
        db.execute(
            """INSERT OR IGNORE INTO shop_items (id, title, description, cost, effect, repeatable)
               VALUES (?, ?, ?, ?, ?, ?)""",
            row,
        )
    cur = db.execute("SELECT 1 FROM users WHERE role = 'admin' LIMIT 1")
    if cur.fetchone() is None:
        db.execute(
            "INSERT INTO users (name, password_hash, role) VALUES (?, ?, 'admin')",
            ("admin", generate_password_hash(admin_password)),
        )
