"""ランク定義と権限モデル。

積極的に使う人ほど成長が加速する設計だが、Engagement(活動量)と
Authority(組織権限)は別軸として扱う:

- EXP ランクは「活動・貢献度」の指標。個人の恩恵(XPブースター購入)は
  ランク到達で自動解放される
- 「改善提案の承認」「クエスト作成」「コンテンツ管理」「称賛ボーナス付与」は
  他者に影響する組織権限(Authority)であり、ランク到達は
  あくまで「認定候補(eligible)」になるだけ。実際の付与は
  管理者が個別に認定して初めて有効になる(= Skill Certification)
- ポイントで権限そのものを購入することはできない(認定の優先申請は可)
- 管理者(admin ロール)は全権限を持つ
"""

RANKS = [
    {"min": 0,    "key": "bronze",   "name": "ブロンズ",     "title": "見習い探究者",     "color1": "#8a6a3a", "color2": "#c99a52"},
    {"min": 200,  "key": "silver",   "name": "シルバー",     "title": "実践エンジニア",   "color1": "#8b8fa3", "color2": "#dfe3ee"},
    {"min": 600,  "key": "gold",     "name": "ゴールド",     "title": "知識のクラフツマン", "color1": "#b8860b", "color2": "#ffd45e"},
    {"min": 1200, "key": "platinum", "name": "プラチナ",     "title": "エキスパート",     "color1": "#1f8a7a", "color2": "#6df0d6"},
    {"min": 2200, "key": "diamond",  "name": "ダイヤモンド", "title": "マスタークラフター", "color1": "#2b5cc9", "color2": "#8fc4ff"},
    {"min": 4000, "key": "master",   "name": "マスター",     "title": "レジェンド",       "color1": "#6b21c9", "color2": "#ffd45e"},
]

# ランク到達で自動解放される権限(個人の恩恵のみ。組織権限は含まない)
AUTO_PERMISSIONS = {
    "silver": ["buy_boost"],   # XPブースター購入可
}

# 組織権限: ランク到達は「認定候補」になるだけで、実際の付与には
# 管理者の個別認定(POST /api/admin/users/<id>/certify)が必要
GOVERNANCE_PERMISSIONS = {
    "approve_proposals": "gold",      # 改善提案の承認・却下権限
    "create_quests":     "platinum",  # クエスト作成権限
    "manage_contents":   "platinum",  # コンテンツ登録・管理権限
    "mentor":             "master",   # 称賛ボーナス付与権限
}

ALL_PERMISSIONS = {
    "buy_boost":         "XPブースター購入",
    "approve_proposals": "改善提案の承認",
    "create_quests":     "クエストの作成",
    "manage_contents":   "コンテンツの登録・管理",
    "mentor":            "称賛ボーナスの付与",
}

# 後方互換: /api/meta の rank_permissions は「自動解放される権限」のみを返す
RANK_PERMISSIONS = AUTO_PERMISSIONS

# 報酬パラメータ
PROPOSAL_SUBMIT_EXP = 100
PROPOSAL_SUBMIT_PTS = 30
PROPOSAL_ADOPTED_EXP = 180
PROPOSAL_ADOPTED_PTS = 60
APPROVE_REWARD_EXP = 20      # 承認作業をした人への報酬(ガバナンス活動もEXP化)
MENTOR_BONUS_EXP = 30        # メンターが1日1回/相手ごとに贈れる称賛
MENTOR_DAILY_LIMIT = 3       # メンターが1日に贈れる称賛の総回数
PROPOSAL_DAILY_REWARD_LIMIT = 3  # 提案の投稿報酬が付く1日あたりの件数(連投による報酬稼ぎ防止)
BOOST_MULTIPLIER = 1.5


def rank_index(exp: int) -> int:
    idx = 0
    for i, r in enumerate(RANKS):
        if exp >= r["min"]:
            idx = i
    return idx


def rank_info(exp: int) -> dict:
    idx = rank_index(exp)
    cur = RANKS[idx]
    nxt = RANKS[idx + 1] if idx + 1 < len(RANKS) else None
    return {"level": idx + 1, "current": cur, "next": nxt}


def permissions_for(exp: int, role: str, granted: list[str]) -> list[str]:
    """実効権限を返す: 個人の恩恵はランク自動解放、組織権限は認定(granted)必須。

    admin は全権限。granted は「管理者が認定した組織権限」のリスト
    (user_permissions テーブル、source='admin')。
    """
    if role == "admin":
        return sorted(ALL_PERMISSIONS.keys())
    perms = set(p for p in granted if p in GOVERNANCE_PERMISSIONS)
    idx = rank_index(exp)
    for i in range(idx + 1):
        perms.update(AUTO_PERMISSIONS.get(RANKS[i]["key"], []))
    return sorted(perms)


def eligible_governance_permissions(exp: int) -> list[str]:
    """ランク到達により「認定候補」になっている組織権限のキー一覧。

    候補であることは自動付与を意味しない — 管理者の認定が別途必要。
    """
    idx = rank_index(exp)
    reached = {RANKS[i]["key"] for i in range(idx + 1)}
    return sorted(p for p, need_rank in GOVERNANCE_PERMISSIONS.items() if need_rank in reached)
