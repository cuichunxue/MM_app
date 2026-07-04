"""ランク定義と権限モデル。

積極的に使う人ほど権限が増え、成長が加速する設計:
- EXP ランク到達で権限が自動解放される(下がらない)
- ポイントでショップから権限を先行購入できる
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

# ランク到達で自動解放される権限
RANK_PERMISSIONS = {
    "silver":   ["buy_boost"],           # XPブースター購入可
    "gold":     ["approve_proposals"],   # 改善提案の承認・却下権限
    "platinum": ["create_quests"],       # クエスト作成権限
    "master":   ["mentor"],              # 称賛ボーナス付与権限
}

ALL_PERMISSIONS = {
    "buy_boost":         "XPブースター購入",
    "approve_proposals": "改善提案の承認",
    "create_quests":     "クエストの作成",
    "mentor":            "称賛ボーナスの付与",
}

# 報酬パラメータ
PROPOSAL_SUBMIT_EXP = 100
PROPOSAL_SUBMIT_PTS = 30
PROPOSAL_ADOPTED_EXP = 180
PROPOSAL_ADOPTED_PTS = 60
APPROVE_REWARD_EXP = 20      # 承認作業をした人への報酬(ガバナンス活動もEXP化)
MENTOR_BONUS_EXP = 30        # メンターが1日1回/相手ごとに贈れる称賛
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
    """ランク自動解放 + 個別付与 + admin 全権限をまとめて返す。"""
    if role == "admin":
        return sorted(ALL_PERMISSIONS.keys())
    perms = set(granted)
    idx = rank_index(exp)
    for i in range(idx + 1):
        perms.update(RANK_PERMISSIONS.get(RANKS[i]["key"], []))
    return sorted(perms)
