"""ゲームAPI: クエスト・改善提案・ショップ・ランキング・管理。"""
from flask import Blueprint, jsonify, request

from .auth import (
    admin_required, current_user, login_required, permission_required,
    user_permissions,
)
from .db import get_db
from .permissions import (
    ALL_PERMISSIONS, APPROVE_REWARD_EXP, BOOST_MULTIPLIER, MENTOR_BONUS_EXP,
    PROPOSAL_ADOPTED_EXP, PROPOSAL_ADOPTED_PTS, PROPOSAL_SUBMIT_EXP,
    PROPOSAL_SUBMIT_PTS, RANKS, rank_index, rank_info,
)

bp = Blueprint("api", __name__, url_prefix="/api")


# ---- 共通: 報酬付与(ブースター適用 + 監査ログ) ----

def award(db, user, exp: int, pts: int, type_: str, ref: str = None, note: str = None,
          use_boost: bool = False) -> dict:
    boosted = False
    if use_boost and exp > 0 and user["boost_charges"] > 0:
        exp = round(exp * BOOST_MULTIPLIER)
        boosted = True
        db.execute("UPDATE users SET boost_charges = boost_charges - 1 WHERE id = ?", (user["id"],))
    db.execute(
        "UPDATE users SET exp = exp + ?, points = points + ? WHERE id = ?",
        (exp, pts, user["id"]),
    )
    db.execute(
        "INSERT INTO ledger (user_id, type, ref, delta_exp, delta_points, note) VALUES (?, ?, ?, ?, ?, ?)",
        (user["id"], type_, ref, exp, pts, note),
    )
    return {"exp": exp, "pts": pts, "boosted": boosted}


def _badges(db, user) -> list[dict]:
    completed = {
        r["quest_id"]
        for r in db.execute(
            "SELECT DISTINCT quest_id FROM quest_completions WHERE user_id = ?", (user["id"],)
        ).fetchall()
    }
    n_proposals = db.execute(
        "SELECT COUNT(*) c FROM proposals WHERE user_id = ?", (user["id"],)
    ).fetchone()["c"]
    n_adopted = db.execute(
        "SELECT COUNT(*) c FROM proposals WHERE user_id = ? AND status = 'approved'", (user["id"],)
    ).fetchone()["c"]
    defs = [
        ("b_first",    "🔰", "はじめの一歩",       len(completed) >= 1),
        ("b_reader",   "📚", "読書家",             "q_read_doc" in completed),
        ("b_sharer",   "🎤", "伝道師",             "q_share" in completed),
        ("b_proposer", "💡", "改善提案者",         n_proposals >= 1),
        ("b_adopted",  "🏆", "採用実績あり",       n_adopted >= 1),
        ("b_meister",  "📈", "カイゼンマイスター", n_adopted >= 1 and {"q_kaizen_report", "q_kaizen_practice"} <= completed),
    ]
    return [{"id": i, "icon": ic, "name": nm, "unlocked": ok} for i, ic, nm, ok in defs]


def _user_payload(db, user) -> dict:
    user = db.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    return {
        "id": user["id"],
        "name": user["name"],
        "role": user["role"],
        "exp": user["exp"],
        "points": user["points"],
        "boost_charges": user["boost_charges"],
        "rank": rank_info(user["exp"]),
        "permissions": user_permissions(user),
        "badges": _badges(db, user),
    }


@bp.get("/meta")
def meta():
    return jsonify(ranks=RANKS, permission_labels=ALL_PERMISSIONS)


@bp.get("/me")
@login_required
def me():
    db = get_db()
    return jsonify(_user_payload(db, current_user()))


# ---- クエスト ----

@bp.get("/quests")
@login_required
def list_quests():
    db = get_db()
    user = current_user()
    quests = db.execute(
        """SELECT q.*, c.title AS content_title, c.url AS content_url
           FROM quests q LEFT JOIN contents c ON c.id = q.content_id
           WHERE q.active = 1 ORDER BY q.rowid"""
    ).fetchall()
    out = []
    for q in quests:
        last = db.execute(
            "SELECT MAX(completed_at) t FROM quest_completions WHERE user_id = ? AND quest_id = ?",
            (user["id"], q["id"]),
        ).fetchone()["t"]
        available, next_at = True, None
        if last is not None:
            if q["cooldown_hours"] is None:
                available = False
            else:
                row = db.execute(
                    "SELECT (julianday('now') - julianday(?)) * 24 AS h", (last,)
                ).fetchone()
                if row["h"] < q["cooldown_hours"]:
                    available = False
                    next_at = db.execute(
                        "SELECT datetime(?, '+' || ? || ' hours') t", (last, q["cooldown_hours"])
                    ).fetchone()["t"]
        out.append({
            "id": q["id"], "title": q["title"], "description": q["description"],
            "exp": q["exp"], "pts": q["pts"], "category": q["category"],
            "repeatable": q["cooldown_hours"] is not None,
            "cooldown_hours": q["cooldown_hours"],
            "available": available, "done_once": last is not None, "next_available_at": next_at,
            "content_title": q["content_title"], "content_url": q["content_url"],
        })
    return jsonify(quests=out)


@bp.post("/quests/<quest_id>/complete")
@login_required
def complete_quest(quest_id):
    db = get_db()
    user = current_user()
    q = db.execute("SELECT * FROM quests WHERE id = ? AND active = 1", (quest_id,)).fetchone()
    if q is None:
        return jsonify(error="クエストが見つかりません"), 404
    last = db.execute(
        "SELECT MAX(completed_at) t FROM quest_completions WHERE user_id = ? AND quest_id = ?",
        (user["id"], quest_id),
    ).fetchone()["t"]
    if last is not None:
        if q["cooldown_hours"] is None:
            return jsonify(error="このクエストは完了済みです"), 409
        row = db.execute("SELECT (julianday('now') - julianday(?)) * 24 AS h", (last,)).fetchone()
        if row["h"] < q["cooldown_hours"]:
            return jsonify(error="クールダウン中です。時間をおいて再挑戦してください"), 429

    before = rank_index(user["exp"])
    db.execute(
        "INSERT INTO quest_completions (user_id, quest_id) VALUES (?, ?)",
        (user["id"], quest_id),
    )
    result = award(db, user, q["exp"], q["pts"], "quest", ref=quest_id,
                   note=q["title"], use_boost=True)
    db.commit()
    payload = _user_payload(db, user)
    return jsonify(ok=True, awarded=result,
                   rank_up=rank_index(payload["exp"]) > before, me=payload)


@bp.post("/quests")
@permission_required("create_quests")
def create_quest():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    desc = (data.get("description") or "").strip()
    try:
        exp = int(data.get("exp", 0))
        pts = int(data.get("pts", 0))
    except (TypeError, ValueError):
        return jsonify(error="EXP/ポイントは数値で指定してください"), 400
    category = data.get("category") or "usage"
    cooldown = data.get("cooldown_hours")
    if not title or not desc:
        return jsonify(error="タイトルと説明は必須です"), 400
    if not (1 <= exp <= 300) or not (0 <= pts <= 100):
        return jsonify(error="EXPは1〜300、ポイントは0〜100の範囲で設定してください"), 400
    if category not in ("usage", "learning", "kaizen"):
        return jsonify(error="カテゴリが不正です"), 400
    if cooldown is not None:
        try:
            cooldown = int(cooldown)
        except (TypeError, ValueError):
            return jsonify(error="クールダウンは数値で指定してください"), 400
        if cooldown < 1:
            cooldown = None
    db = get_db()
    user = current_user()
    quest_id = "q_custom_" + str(db.execute("SELECT COALESCE(MAX(rowid),0)+1 n FROM quests").fetchone()["n"])
    db.execute(
        """INSERT INTO quests (id, title, description, exp, pts, category, cooldown_hours, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (quest_id, title, desc, exp, pts, category, cooldown, user["id"]),
    )
    db.commit()
    return jsonify(ok=True, id=quest_id), 201


# ---- コンテンツ(社内ツール・記事・動画) ----

CONTENT_TYPES = ("tool", "article", "video")
# 自動生成クエストの既定値: (exp, pts, cooldown_hours, category)
CONTENT_QUEST_DEFAULTS = {
    "tool":    (30, 10, 24,   "usage"),
    "article": (40, 12, None, "learning"),
    "video":   (40, 12, None, "learning"),
}


@bp.get("/contents")
@login_required
def list_contents():
    db = get_db()
    user = current_user()
    can_manage = "manage_contents" in user_permissions(user)
    where = "" if can_manage else "WHERE c.active = 1"
    rows = db.execute(
        f"""SELECT c.*, u.name AS author, q.id AS quest_id
            FROM contents c
            LEFT JOIN users u ON u.id = c.created_by
            LEFT JOIN quests q ON q.content_id = c.id
            {where} ORDER BY c.created_at DESC"""
    ).fetchall()
    return jsonify(can_manage=can_manage, items=[{
        "id": r["id"], "title": r["title"], "type": r["type"], "url": r["url"],
        "description": r["description"], "active": bool(r["active"]),
        "author": r["author"], "quest_id": r["quest_id"], "created_at": r["created_at"],
    } for r in rows])


@bp.post("/contents")
@permission_required("manage_contents")
def create_content():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    type_ = data.get("type")
    url = (data.get("url") or "").strip() or None
    desc = (data.get("description") or "").strip()
    if not title or len(title) > 80:
        return jsonify(error="タイトルは1〜80文字で入力してください"), 400
    if type_ not in CONTENT_TYPES:
        return jsonify(error="type は tool / article / video を指定してください"), 400
    if url and not (url.startswith("http://") or url.startswith("https://")):
        return jsonify(error="URLは http(s):// で始まる形式で入力してください"), 400
    db = get_db()
    user = current_user()
    cur = db.execute(
        "INSERT INTO contents (title, type, url, description, created_by) VALUES (?, ?, ?, ?, ?)",
        (title, type_, url, desc, user["id"]),
    )
    content_id = cur.lastrowid

    quest_id = None
    if data.get("auto_quest", True):
        d_exp, d_pts, d_cd, d_cat = CONTENT_QUEST_DEFAULTS[type_]
        try:
            exp = int(data.get("quest_exp", d_exp))
            pts = int(data.get("quest_pts", d_pts))
        except (TypeError, ValueError):
            return jsonify(error="EXP/ポイントは数値で指定してください"), 400
        if not (1 <= exp <= 300) or not (0 <= pts <= 100):
            return jsonify(error="EXPは1〜300、ポイントは0〜100の範囲で設定してください"), 400
        verb = {"tool": "を使ってみる", "article": "を読了する", "video": "を視聴する"}[type_]
        quest_id = f"q_content_{content_id}"
        db.execute(
            """INSERT INTO quests (id, title, description, exp, pts, category, cooldown_hours, created_by, content_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (quest_id, f"「{title}」{verb}", desc or f"登録コンテンツ「{title}」に取り組む",
             exp, pts, d_cat, d_cd, user["id"], content_id),
        )
    db.commit()
    return jsonify(ok=True, id=content_id, quest_id=quest_id), 201


@bp.patch("/contents/<int:cid>")
@permission_required("manage_contents")
def update_content(cid):
    db = get_db()
    c = db.execute("SELECT * FROM contents WHERE id = ?", (cid,)).fetchone()
    if c is None:
        return jsonify(error="コンテンツが見つかりません"), 404
    data = request.get_json(silent=True) or {}
    fields, values = [], []
    if "title" in data:
        title = (data["title"] or "").strip()
        if not title or len(title) > 80:
            return jsonify(error="タイトルは1〜80文字で入力してください"), 400
        fields.append("title = ?"); values.append(title)
    if "url" in data:
        url = (data["url"] or "").strip() or None
        if url and not (url.startswith("http://") or url.startswith("https://")):
            return jsonify(error="URLは http(s):// で始まる形式で入力してください"), 400
        fields.append("url = ?"); values.append(url)
    if "description" in data:
        fields.append("description = ?"); values.append((data["description"] or "").strip())
    if "type" in data:
        if data["type"] not in CONTENT_TYPES:
            return jsonify(error="type は tool / article / video を指定してください"), 400
        fields.append("type = ?"); values.append(data["type"])
    if "active" in data:
        active = 1 if data["active"] else 0
        fields.append("active = ?"); values.append(active)
        # 紐付くクエストも連動して有効/無効化
        db.execute("UPDATE quests SET active = ? WHERE content_id = ?", (active, cid))
    if not fields:
        return jsonify(error="更新する項目がありません"), 400
    values.append(cid)
    db.execute(f"UPDATE contents SET {', '.join(fields)} WHERE id = ?", values)
    db.commit()
    return jsonify(ok=True)


# ---- 改善提案 ----

@bp.get("/proposals")
@login_required
def list_proposals():
    db = get_db()
    user = current_user()
    can_review = "approve_proposals" in user_permissions(user)
    rows = db.execute(
        """SELECT p.*, u.name AS author, r.name AS reviewer
           FROM proposals p
           JOIN users u ON u.id = p.user_id
           LEFT JOIN users r ON r.id = p.reviewed_by
           ORDER BY p.created_at DESC LIMIT 50"""
    ).fetchall()
    return jsonify(
        can_review=can_review,
        proposals=[{
            "id": r["id"], "author": r["author"], "text": r["text"],
            "status": r["status"], "created_at": r["created_at"],
            "reviewer": r["reviewer"], "mine": r["user_id"] == user["id"],
        } for r in rows],
    )


@bp.post("/proposals")
@login_required
def submit_proposal():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify(error="提案内容を入力してください"), 400
    if len(text) > 1000:
        return jsonify(error="提案は1000文字以内で入力してください"), 400
    db = get_db()
    user = current_user()
    before = rank_index(user["exp"])
    db.execute("INSERT INTO proposals (user_id, text) VALUES (?, ?)", (user["id"], text))
    award(db, user, PROPOSAL_SUBMIT_EXP, PROPOSAL_SUBMIT_PTS, "proposal_submit")
    db.commit()
    payload = _user_payload(db, user)
    return jsonify(ok=True, rank_up=rank_index(payload["exp"]) > before, me=payload), 201


@bp.post("/proposals/<int:pid>/review")
@permission_required("approve_proposals")
def review_proposal(pid):
    data = request.get_json(silent=True) or {}
    decision = data.get("decision")
    if decision not in ("approved", "rejected"):
        return jsonify(error="decision は approved / rejected を指定してください"), 400
    db = get_db()
    user = current_user()
    p = db.execute("SELECT * FROM proposals WHERE id = ?", (pid,)).fetchone()
    if p is None:
        return jsonify(error="提案が見つかりません"), 404
    if p["status"] != "pending":
        return jsonify(error="この提案は審査済みです"), 409
    if p["user_id"] == user["id"]:
        return jsonify(error="自分の提案は承認できません"), 403
    db.execute(
        "UPDATE proposals SET status = ?, reviewed_by = ?, reviewed_at = datetime('now') WHERE id = ?",
        (decision, user["id"], pid),
    )
    if decision == "approved":
        author = db.execute("SELECT * FROM users WHERE id = ?", (p["user_id"],)).fetchone()
        award(db, author, PROPOSAL_ADOPTED_EXP, PROPOSAL_ADOPTED_PTS,
              "proposal_adopted", ref=str(pid))
    award(db, user, APPROVE_REWARD_EXP, 0, "approve_reward", ref=str(pid))
    db.commit()
    return jsonify(ok=True, me=_user_payload(db, user))


# ---- ショップ ----

@bp.get("/shop")
@login_required
def list_shop():
    db = get_db()
    user = current_user()
    perms = user_permissions(user)
    items = db.execute("SELECT * FROM shop_items WHERE active = 1 ORDER BY cost").fetchall()
    redeemed = {
        r["item_id"]
        for r in db.execute("SELECT DISTINCT item_id FROM redemptions WHERE user_id = ?", (user["id"],)).fetchall()
    }
    out = []
    for it in items:
        locked_reason = None
        if it["effect"] == "boost5" and "buy_boost" not in perms:
            locked_reason = "シルバー到達で購入可能になります"
        if it["effect"] == "grant:approve_proposals" and "approve_proposals" in perms:
            locked_reason = "既に承認権限を持っています"
        out.append({
            "id": it["id"], "title": it["title"], "description": it["description"],
            "cost": it["cost"], "repeatable": bool(it["repeatable"]),
            "redeemed": it["id"] in redeemed, "locked_reason": locked_reason,
        })
    return jsonify(items=out)


@bp.post("/shop/<item_id>/redeem")
@login_required
def redeem(item_id):
    db = get_db()
    user = current_user()
    it = db.execute("SELECT * FROM shop_items WHERE id = ? AND active = 1", (item_id,)).fetchone()
    if it is None:
        return jsonify(error="アイテムが見つかりません"), 404
    if not it["repeatable"]:
        if db.execute(
            "SELECT 1 FROM redemptions WHERE user_id = ? AND item_id = ?", (user["id"], item_id)
        ).fetchone():
            return jsonify(error="このアイテムは交換済みです"), 409
    perms = user_permissions(user)
    if it["effect"] == "boost5" and "buy_boost" not in perms:
        return jsonify(error="XPブースターはシルバー到達で購入可能になります"), 403
    if it["effect"] == "grant:approve_proposals" and "approve_proposals" in perms:
        return jsonify(error="既に承認権限を持っています"), 409
    if user["points"] < it["cost"]:
        return jsonify(error="ポイントが不足しています"), 400

    db.execute("INSERT INTO redemptions (user_id, item_id) VALUES (?, ?)", (user["id"], item_id))
    award(db, user, 0, -it["cost"], "shop", ref=item_id, note=it["title"])
    if it["effect"] == "boost5":
        db.execute("UPDATE users SET boost_charges = boost_charges + 5 WHERE id = ?", (user["id"],))
    elif it["effect"] and it["effect"].startswith("grant:"):
        db.execute(
            "INSERT OR IGNORE INTO user_permissions (user_id, permission, source) VALUES (?, ?, 'shop')",
            (user["id"], it["effect"].split(":", 1)[1]),
        )
    db.commit()
    return jsonify(ok=True, me=_user_payload(db, current_user()))


# ---- ランキング・アクティビティ ----

@bp.get("/leaderboard")
@login_required
def leaderboard():
    db = get_db()
    user = current_user()
    rows = db.execute(
        "SELECT id, name, exp FROM users WHERE role != 'admin' ORDER BY exp DESC, name LIMIT 10"
    ).fetchall()
    return jsonify(rows=[{
        "id": r["id"], "name": r["name"], "exp": r["exp"],
        "level": rank_index(r["exp"]) + 1, "me": r["id"] == user["id"],
    } for r in rows])


@bp.get("/activity")
@login_required
def activity():
    db = get_db()
    user = current_user()
    rows = db.execute(
        "SELECT type, ref, delta_exp, delta_points, note, created_at FROM ledger "
        "WHERE user_id = ? ORDER BY id DESC LIMIT 30",
        (user["id"],),
    ).fetchall()
    return jsonify(rows=[dict(r) for r in rows])


# ---- メンター(称賛ボーナス) ----

@bp.post("/users/<int:target_id>/praise")
@permission_required("mentor")
def praise(target_id):
    db = get_db()
    user = current_user()
    if target_id == user["id"]:
        return jsonify(error="自分自身は称賛できません"), 400
    target = db.execute("SELECT * FROM users WHERE id = ?", (target_id,)).fetchone()
    if target is None:
        return jsonify(error="ユーザーが見つかりません"), 404
    already = db.execute(
        """SELECT 1 FROM ledger WHERE user_id = ? AND type = 'mentor_bonus'
           AND ref = ? AND date(created_at) = date('now')""",
        (target_id, str(user["id"])),
    ).fetchone()
    if already:
        return jsonify(error="この相手への称賛は今日はもう贈っています"), 429
    award(db, target, MENTOR_BONUS_EXP, 0, "mentor_bonus", ref=str(user["id"]),
          note=f"{user['name']} からの称賛")
    db.commit()
    return jsonify(ok=True)


# ---- 管理者 ----

@bp.get("/admin/users")
@admin_required
def admin_users():
    db = get_db()
    rows = db.execute(
        "SELECT id, name, role, exp, points, created_at FROM users ORDER BY exp DESC"
    ).fetchall()
    return jsonify(users=[dict(r) | {"level": rank_index(r["exp"]) + 1} for r in rows])


@bp.post("/admin/users/<int:uid>/role")
@admin_required
def admin_set_role(uid):
    data = request.get_json(silent=True) or {}
    role = data.get("role")
    if role not in ("member", "admin"):
        return jsonify(error="role は member / admin を指定してください"), 400
    db = get_db()
    if db.execute("SELECT 1 FROM users WHERE id = ?", (uid,)).fetchone() is None:
        return jsonify(error="ユーザーが見つかりません"), 404
    db.execute("UPDATE users SET role = ? WHERE id = ?", (role, uid))
    db.commit()
    return jsonify(ok=True)


@bp.get("/admin/quests")
@admin_required
def admin_quests():
    db = get_db()
    rows = db.execute(
        """SELECT q.*, c.title AS content_title FROM quests q
           LEFT JOIN contents c ON c.id = q.content_id ORDER BY q.rowid"""
    ).fetchall()
    return jsonify(quests=[{
        "id": r["id"], "title": r["title"], "description": r["description"],
        "exp": r["exp"], "pts": r["pts"], "category": r["category"],
        "cooldown_hours": r["cooldown_hours"], "active": bool(r["active"]),
        "content_title": r["content_title"],
    } for r in rows])


@bp.patch("/admin/quests/<quest_id>")
@admin_required
def admin_update_quest(quest_id):
    db = get_db()
    if db.execute("SELECT 1 FROM quests WHERE id = ?", (quest_id,)).fetchone() is None:
        return jsonify(error="クエストが見つかりません"), 404
    data = request.get_json(silent=True) or {}
    fields, values = [], []
    if "title" in data:
        title = (data["title"] or "").strip()
        if not title:
            return jsonify(error="タイトルは必須です"), 400
        fields.append("title = ?"); values.append(title)
    if "description" in data:
        fields.append("description = ?"); values.append((data["description"] or "").strip())
    for key, lo, hi, label in (("exp", 1, 300, "EXPは1〜300"), ("pts", 0, 100, "ポイントは0〜100")):
        if key in data:
            try:
                v = int(data[key])
            except (TypeError, ValueError):
                return jsonify(error=f"{key} は数値で指定してください"), 400
            if not (lo <= v <= hi):
                return jsonify(error=f"{label}の範囲で設定してください"), 400
            fields.append(f"{key} = ?"); values.append(v)
    if "cooldown_hours" in data:
        cd = data["cooldown_hours"]
        if cd is not None:
            try:
                cd = int(cd)
            except (TypeError, ValueError):
                return jsonify(error="クールダウンは数値で指定してください"), 400
            if cd < 1:
                cd = None
        fields.append("cooldown_hours = ?"); values.append(cd)
    if "active" in data:
        fields.append("active = ?"); values.append(1 if data["active"] else 0)
    if not fields:
        return jsonify(error="更新する項目がありません"), 400
    values.append(quest_id)
    db.execute(f"UPDATE quests SET {', '.join(fields)} WHERE id = ?", values)
    db.commit()
    return jsonify(ok=True)


@bp.get("/admin/shop")
@admin_required
def admin_shop():
    db = get_db()
    rows = db.execute("SELECT * FROM shop_items ORDER BY rowid").fetchall()
    return jsonify(items=[dict(r) for r in rows])


@bp.post("/admin/shop")
@admin_required
def admin_create_shop_item():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    desc = (data.get("description") or "").strip()
    try:
        cost = int(data.get("cost", 0))
    except (TypeError, ValueError):
        return jsonify(error="コストは数値で指定してください"), 400
    if not title or not desc:
        return jsonify(error="タイトルと説明は必須です"), 400
    if not (1 <= cost <= 500):
        return jsonify(error="コストは1〜500ptの範囲で設定してください"), 400
    db = get_db()
    item_id = "s_custom_" + str(db.execute("SELECT COALESCE(MAX(rowid),0)+1 n FROM shop_items").fetchone()["n"])
    db.execute(
        "INSERT INTO shop_items (id, title, description, cost, repeatable) VALUES (?, ?, ?, ?, ?)",
        (item_id, title, desc, cost, 1 if data.get("repeatable") else 0),
    )
    db.commit()
    return jsonify(ok=True, id=item_id), 201


@bp.patch("/admin/shop/<item_id>")
@admin_required
def admin_update_shop_item(item_id):
    db = get_db()
    if db.execute("SELECT 1 FROM shop_items WHERE id = ?", (item_id,)).fetchone() is None:
        return jsonify(error="アイテムが見つかりません"), 404
    data = request.get_json(silent=True) or {}
    fields, values = [], []
    if "title" in data:
        title = (data["title"] or "").strip()
        if not title:
            return jsonify(error="タイトルは必須です"), 400
        fields.append("title = ?"); values.append(title)
    if "description" in data:
        fields.append("description = ?"); values.append((data["description"] or "").strip())
    if "cost" in data:
        try:
            cost = int(data["cost"])
        except (TypeError, ValueError):
            return jsonify(error="コストは数値で指定してください"), 400
        if not (1 <= cost <= 500):
            return jsonify(error="コストは1〜500ptの範囲で設定してください"), 400
        fields.append("cost = ?"); values.append(cost)
    if "repeatable" in data:
        fields.append("repeatable = ?"); values.append(1 if data["repeatable"] else 0)
    if "active" in data:
        fields.append("active = ?"); values.append(1 if data["active"] else 0)
    if not fields:
        return jsonify(error="更新する項目がありません"), 400
    values.append(item_id)
    db.execute(f"UPDATE shop_items SET {', '.join(fields)} WHERE id = ?", values)
    db.commit()
    return jsonify(ok=True)


@bp.get("/admin/stats")
@admin_required
def admin_stats():
    db = get_db()
    n_users = db.execute("SELECT COUNT(*) c FROM users WHERE role != 'admin'").fetchone()["c"]
    n_completions = db.execute("SELECT COUNT(*) c FROM quest_completions").fetchone()["c"]
    n_proposals = db.execute("SELECT COUNT(*) c FROM proposals").fetchone()["c"]
    n_approved = db.execute("SELECT COUNT(*) c FROM proposals WHERE status='approved'").fetchone()["c"]
    weekly = db.execute(
        """SELECT date(created_at) d, COUNT(DISTINCT user_id) c FROM ledger
           WHERE created_at >= datetime('now', '-7 days') GROUP BY d ORDER BY d"""
    ).fetchall()
    return jsonify(
        users=n_users, quest_completions=n_completions,
        proposals=n_proposals, proposals_approved=n_approved,
        weekly_active=[dict(r) for r in weekly],
    )
