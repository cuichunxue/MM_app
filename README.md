# LEVEL UP LAB — 社内データ活用促進アプリ

社内ツールの利用・学習・改善活動をゲーミフィケーションで促進するフルスタックアプリです。
**使う・学ぶ・改善するほど EXP とポイントが貯まり、称号(ランク)が上がって成長が加速する**設計になっています。

Engagement(活動量)と Authority(組織権限)は別軸として扱います。ランクは活動・貢献度の指標であり、
改善提案の承認やクエスト作成などの組織権限は**ランク到達だけでは付与されず、管理者の個別認定が必須**です
(詳細は「ガバナンスモデル」節を参照)。

## アーキテクチャ

| レイヤ | 技術 | 場所 |
|---|---|---|
| フロントエンド | バニラ JS SPA(フレームワークなし) | `static/` |
| バックエンド | Flask(アプリケーションファクトリ + Blueprint) | `backend/` |
| データベース | SQLite(スキーマ: `backend/schema.sql`) | `instance/levelup.db`(自動生成) |
| 認証 | セッショントークン(HttpOnly Cookie)+ werkzeug パスワードハッシュ | `backend/auth.py` |
| テスト | unittest + Flask test client(40ケース) | `tests/` |

## セットアップ(開発用)

```bash
pip install -r requirements.txt
python3 app.py            # http://localhost:5000
```

初回起動時に DB スキーマ・シードデータ(クエスト/ショップ)・管理者アカウントが自動作成されます。

| 環境変数 | 既定値 | 説明 |
|---|---|---|
| `DATABASE` | `instance/levelup.db` | SQLite ファイルパス |
| `ADMIN_PASSWORD` | ランダム生成 | 初期 admin のパスワード。未設定なら初回起動時に生成され**起動ログに一度だけ表示** |
| `SECRET_KEY` | 起動ごとにランダム生成 | Flask シークレット(固定したい場合のみ設定) |
| `COOKIE_SECURE` | 未設定 | `1` でセッションCookieに `Secure` 属性を強制(HTTPSリバースプロキシ配下で設定) |
| `FLASK_DEBUG` | 未設定 | `1` のときだけ `python3 app.py` がデバッグモードになる(既定は無効) |

テスト実行: `python3 -m unittest discover tests`

## ゲームデザイン

### ランク(累計EXP・下がらない)

| LV | ランク | 称号 | 必要EXP | 自動解放される個人の恩恵 | 認定候補になる組織権限 |
|---|---|---|---|---|---|
| 1 | ブロンズ | 見習い探究者 | 0 | — | — |
| 2 | シルバー | 実践エンジニア | 200 | XPブースター購入 | — |
| 3 | ゴールド | 知識のクラフツマン | 600 | — | 改善提案の承認・却下(候補) |
| 4 | プラチナ | エキスパート | 1,200 | — | クエスト作成・コンテンツ登録(候補) |
| 5 | ダイヤモンド | マスタークラフター | 2,200 | — | — |
| 6 | マスター | レジェンド | 4,000 | — | 称賛ボーナスの付与(候補) |

### ガバナンスモデル: Engagement ≠ Authority

活動量(EXP)だけで組織権限が手に入ると、「たくさん投稿した人」が「承認する側」に
自動的に回ってしまい、Engagement・Competence・Authority が事実上同一視されてしまいます。
これを避けるため、権限は2種類に分けています。

| 種別 | 内容 | 付与条件 |
|---|---|---|
| 個人の恩恵(AUTO_PERMISSIONS) | XPブースター購入など、本人にしか影響しない | ランク到達で自動解放(従来どおり) |
| 組織権限(GOVERNANCE_PERMISSIONS) | 改善提案の承認・クエスト作成・コンテンツ管理・称賛付与など、他者に影響する | ランク到達は「認定候補」になるだけ。**管理者が `POST /api/admin/users/<id>/certify` で個別に認定して初めて有効** |

- ランクが下がることはないのと同様、認定も自動失効しません。ただし管理者はいつでも取り消せます(`grant: false`)
- ポイントで組織権限そのものを買うことはできません。買えるのは「認定の優先申請」(ショップの `priority:<permission>` 効果)のみで、
  管理者の認定キューに乗るだけです
- 管理者(admin ロール)は認定不要で全権限を持ちます
- `GET /api/me` の `eligible_permissions` で「候補だが未認定」の権限が分かり、UI では権限チップに 🎖(候補)/ ✓(認定済み)/ 🔒(未到達)で表示されます

### 成長加速ループ(積極的なユーザーほど速くなる仕組み)

1. **ランク到達で認定候補になる** — 承認権限・クエスト作成権限などは「候補」までランクで進み、実際の付与は管理者の認定で完了する
2. **ポイントで認定を優先申請できる** — 承認者認定の優先申請(150pt)でゴールド到達を待たずに管理者の審査キューに乗れる(自動付与ではない)
3. **XPブースター** — ポイントで購入すると次の5クエストの EXP が 1.5 倍
4. **ガバナンス活動もEXP化** — 提案を審査した承認者にも +20 EXP(承認する側にもインセンティブ)
5. **メンター称賛** — 認定されたメンターは他メンバーに 1日3回まで(相手ごと1日1回)+30 EXP を贈れる(上位者が下位者を引き上げる)

### 不正防止(サーバー側で検証)

- クエストは1回限り or クールダウン制(繰り返し可のものは時間制限)をサーバーが強制
- 自分の提案は承認できない/二重審査は拒否
- 全 EXP・ポイント増減は `ledger` テーブルに監査ログとして記録
- ランキング・承認・権限判定はすべて API 側で実施(クライアント改ざん不可)
- 書き込みは `BEGIN IMMEDIATE` トランザクションで直列化し、並行リクエストによる
  ポイント二重消費・クエスト二重完了・ブースター残数の負値化を防止
  (残高・残数の減算は `UPDATE ... WHERE points >= ?` 型の条件付き1文で実行)
- 提案の投稿報酬は1日3件まで(投稿自体は無制限)、称賛は1日3回まで
- 最後の管理者は降格不可(ロックアウト防止)

## API 概要

| メソッド/パス | 権限 | 説明 |
|---|---|---|
| `POST /api/auth/register` `login` `logout` | — | 認証 |
| `POST /api/auth/password` / `PATCH /api/auth/profile` | ログイン | 自分のパスワード変更・表示名変更 |
| `GET /api/me` | ログイン | 自分の状態(ランク・権限・認定候補・バッジ・未読通知) |
| `POST /api/me/ack-events` | ログイン | おかえり通知(採用・称賛)の既読化 |
| `GET /api/quests` / `POST /api/quests/<id>/complete` | ログイン | クエスト一覧・完了 |
| `POST /api/quests` | `create_quests` | クエスト作成 |
| `GET /api/contents` | ログイン | コンテンツ(ツール/記事/動画)一覧 |
| `POST /api/contents` / `PATCH /api/contents/<id>` | `manage_contents` | コンテンツ登録・編集・アーカイブ(対応クエスト自動生成) |
| `GET/POST /api/proposals` | ログイン | 改善提案の閲覧・投稿 |
| `PATCH/DELETE /api/proposals/<id>` | 本人(審査前のみ) | 提案の編集・取り下げ(取り下げ時は投稿報酬を返還) |
| `POST /api/proposals/<id>/review` | `approve_proposals` | 採用/見送り |
| `GET /api/shop` / `POST /api/shop/<id>/redeem` | ログイン | ショップ |
| `GET /api/leaderboard` / `GET /api/activity` | ログイン | ランキング・自分の履歴 |
| `POST /api/users/<id>/praise` | `mentor` | 称賛ボーナス |
| `GET /api/admin/users` `stats` / `POST /api/admin/users/<id>/role` | admin | メンバー管理(最終活動日・認定候補・申請状況つき)・統計・14日トレンド |
| `POST /api/admin/users/<id>/certify` | admin | 組織権限の認定・取り消し(`{permission, grant}`) |
| `POST /api/admin/users/<id>/password` | admin | パスワード再設定(本人が忘れた場合。既存セッションは全無効化) |
| `POST /api/admin/users/<id>/adjust` | admin | 手動EXP/pt調整(理由必須・本人に通知・台帳記録) |
| `GET /api/admin/redemptions` / `POST .../<id>/fulfill` | admin | ショップ交換の対応状況管理(ブースター等は自動履行) |
| `GET /api/announcements` / `POST・PATCH /api/admin/announcements` | ログイン / admin | お知らせの閲覧・配信・掲載終了 |
| `GET /api/admin/export/users` `ledger` | admin | CSVエクスポート(BOM付きUTF-8、Excel対応) |
| `GET/PATCH /api/admin/quests(/<id>)` | admin | クエストの報酬調整・有効/無効化 |
| `GET/POST/PATCH /api/admin/shop(/<id>)` | admin | ショップアイテムの追加・価格調整・停止 |

## コンテンツ管理(記事・ツール・動画)

管理者、および `manage_contents` を認定されたメンバー(プラチナ到達で候補になり、
管理者の個別認定で有効化)は、社内ツール・記事・動画を LIBRARY セクションから登録できます。

- 登録時に**対応クエストを自動生成**(ツール→「〜を使ってみる」24h繰り返し、記事/動画→「〜を読了/視聴する」1回限り。EXP/pt は上書き可能)
- コンテンツをアーカイブすると連動クエストも自動停止、再公開で復活
- クエストカードにはコンテンツへのリンクが表示され、メンバーは「開く→取り組む→完了報告」の動線で回遊できます

## 本番デプロイ(Docker不使用)

venv + gunicorn + systemd で動かします。

```bash
git clone <repo> /opt/levelup-lab && cd /opt/levelup-lab
./scripts/setup.sh              # venv作成・依存インストール・.env雛形の配置
vi .env                         # ADMIN_PASSWORD / COOKIE_SECURE=1 などを設定

# 動作確認だけしたい場合はここで:
./scripts/run.sh                # http://<サーバー>:8000 で起動(フォアグラウンド)

# 常駐サービスとして登録する場合:
sudo cp deploy/levelup-lab.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now levelup-lab
sudo journalctl -u levelup-lab -f   # ログ確認(初期adminパスワードはここに一度だけ出力)
```

- SQLite の実体は `instance/levelup.db`(バックアップはこのファイルのコピーだけ)
- `deploy/levelup-lab.service` は `/opt/levelup-lab` 前提のテンプレート。別パスに置く場合は `WorkingDirectory` / `ExecStart` / `EnvironmentFile` を書き換える
- SQLite は社内規模(〜数百人)なら十分。超える場合は PostgreSQL への移行を検討
- HTTPS リバースプロキシ(nginx等)配下では `COOKIE_SECURE=1` を設定し、プロキシ側でTLS終端する
- **パイロット導入の手順・週次運用ルーチン・振り返り観点は [PILOT.md](PILOT.md) を参照**
