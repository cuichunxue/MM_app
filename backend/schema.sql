-- LEVEL UP LAB スキーマ

CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  name          TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role          TEXT NOT NULL DEFAULT 'member',   -- member / admin
  exp           INTEGER NOT NULL DEFAULT 0,
  points        INTEGER NOT NULL DEFAULT 0,
  boost_charges INTEGER NOT NULL DEFAULT 0,       -- XPブースター残回数(1.5倍)
  last_seen_ledger_id INTEGER NOT NULL DEFAULT 0, -- おかえり通知の既読位置
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  expires_at TEXT NOT NULL
);

-- 社内ツール・記事・動画などの活用対象コンテンツ
CREATE TABLE IF NOT EXISTS contents (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  title       TEXT NOT NULL,
  type        TEXT NOT NULL,                      -- tool / article / video
  url         TEXT,
  description TEXT NOT NULL DEFAULT '',
  active      INTEGER NOT NULL DEFAULT 1,
  created_by  INTEGER REFERENCES users(id),
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS quests (
  id             TEXT PRIMARY KEY,
  title          TEXT NOT NULL,
  description    TEXT NOT NULL,
  exp            INTEGER NOT NULL,
  pts            INTEGER NOT NULL,
  category       TEXT NOT NULL,                   -- usage / learning / kaizen
  cooldown_hours INTEGER,                         -- NULL = 1回限り
  active         INTEGER NOT NULL DEFAULT 1,
  created_by     INTEGER REFERENCES users(id),
  content_id     INTEGER REFERENCES contents(id)  -- 紐付くコンテンツ(任意)
);

CREATE TABLE IF NOT EXISTS quest_completions (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  quest_id     TEXT NOT NULL REFERENCES quests(id),
  completed_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_qc_user ON quest_completions(user_id, quest_id, completed_at);

CREATE TABLE IF NOT EXISTS proposals (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  text        TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'pending',    -- pending / approved / rejected
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  reviewed_by INTEGER REFERENCES users(id),
  reviewed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status, created_at);

CREATE TABLE IF NOT EXISTS shop_items (
  id          TEXT PRIMARY KEY,
  title       TEXT NOT NULL,
  description TEXT NOT NULL,
  cost        INTEGER NOT NULL,
  effect      TEXT,                               -- boost5 / priority:<permission> など
  repeatable  INTEGER NOT NULL DEFAULT 0,
  active      INTEGER NOT NULL DEFAULT 1,
  redeem_note TEXT                                -- 購入後の案内(次に何をすべきか)
);

CREATE TABLE IF NOT EXISTS redemptions (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  item_id      TEXT NOT NULL REFERENCES shop_items(id),
  created_at   TEXT NOT NULL DEFAULT (datetime('now')),
  fulfilled_at TEXT,                               -- 運営が特典を履行した日時(NULL=未対応)
  fulfilled_by INTEGER REFERENCES users(id)        -- NULL=自動履行(ブースター等)
);

-- 運営からのお知らせ(キャンペーン告知など)
CREATE TABLE IF NOT EXISTS announcements (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  body       TEXT NOT NULL,
  active     INTEGER NOT NULL DEFAULT 1,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 管理者が個別認定した組織権限(Skill Certification)。
-- ランク到達だけでは付与されず、必ずここに行があって初めて有効になる
CREATE TABLE IF NOT EXISTS user_permissions (
  user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  permission   TEXT NOT NULL,
  granted_at   TEXT NOT NULL DEFAULT (datetime('now')),
  source       TEXT NOT NULL,                     -- admin(常に管理者認定)
  certified_by INTEGER REFERENCES users(id),
  PRIMARY KEY (user_id, permission)
);

-- ポイントで「認定の優先申請」をした記録(権限そのものは付与しない)
CREATE TABLE IF NOT EXISTS certification_requests (
  user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  permission   TEXT NOT NULL,
  requested_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (user_id, permission)
);

-- EXP/ポイントの全増減を記録する監査ログ
CREATE TABLE IF NOT EXISTS ledger (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  type        TEXT NOT NULL,   -- quest / proposal_submit / proposal_adopted / proposal_withdrawn /
                                -- approve_reward / shop / mentor_bonus / admin_adjust /
                                -- admin_certify / admin_decertify
  ref         TEXT,
  delta_exp   INTEGER NOT NULL DEFAULT 0,
  delta_points INTEGER NOT NULL DEFAULT 0,
  note        TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ledger_user ON ledger(user_id, created_at);
