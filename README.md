# LEVEL UP LAB — 社内データ活用促進アプリ

社内ツールの利用・学習・改善活動をゲーミフィケーションで促進するフルスタックアプリです。
**使う・学ぶ・改善するほど EXP とポイントが貯まり、称号(ランク)と「権限」が解放されて成長が加速する**設計になっています。

## アーキテクチャ

| レイヤ | 技術 | 場所 |
|---|---|---|
| フロントエンド | バニラ JS SPA(フレームワークなし) | `static/` |
| バックエンド | Flask(アプリケーションファクトリ + Blueprint) | `backend/` |
| データベース | SQLite(スキーマ: `backend/schema.sql`) | `instance/levelup.db`(自動生成) |
| 認証 | セッショントークン(HttpOnly Cookie)+ werkzeug パスワードハッシュ | `backend/auth.py` |
| テスト | unittest + Flask test client(11ケース) | `tests/` |

## セットアップ

```bash
pip install -r requirements.txt
python3 app.py            # http://localhost:5000
```

初回起動時に DB スキーマ・シードデータ(クエスト/ショップ)・管理者アカウントが自動作成されます。

| 環境変数 | 既定値 | 説明 |
|---|---|---|
| `DATABASE` | `instance/levelup.db` | SQLite ファイルパス |
| `ADMIN_PASSWORD` | `admin1234` | 初期 admin のパスワード(**本番では必ず変更**) |
| `SECRET_KEY` | `dev` | Flask シークレット(本番ではランダム値に) |

テスト実行: `python3 -m unittest discover tests`

## ゲームデザイン

### ランク(累計EXP・下がらない)

| LV | ランク | 称号 | 必要EXP | 解放される権限 |
|---|---|---|---|---|
| 1 | ブロンズ | 見習い探究者 | 0 | — |
| 2 | シルバー | 実践エンジニア | 200 | XPブースター購入 |
| 3 | ゴールド | 知識のクラフツマン | 600 | **改善提案の承認・却下** |
| 4 | プラチナ | エキスパート | 1,200 | **クエストの作成・コンテンツの登録** |
| 5 | ダイヤモンド | マスタークラフター | 2,200 | — |
| 6 | マスター | レジェンド | 4,000 | **称賛ボーナスの付与(メンター)** |

### 成長加速ループ(積極的なユーザーほど速くなる仕組み)

1. **ランク到達で権限が自動解放** — 承認権限・クエスト作成権限などの運営側権限がプレイヤーに移譲される
2. **ポイントで権限を先行購入** — 承認者権限(150pt)はゴールド到達を待たずに買える
3. **XPブースター** — ポイントで購入すると次の5クエストの EXP が 1.5 倍
4. **ガバナンス活動もEXP化** — 提案を審査した承認者にも +20 EXP(承認する側にもインセンティブ)
5. **メンター称賛** — マスター到達者は他メンバーに 1日1回 +30 EXP を贈れる(上位者が下位者を引き上げる)

### 不正防止(サーバー側で検証)

- クエストは1回限り or クールダウン制(繰り返し可のものは時間制限)をサーバーが強制
- 自分の提案は承認できない/二重審査は拒否
- 全 EXP・ポイント増減は `ledger` テーブルに監査ログとして記録
- ランキング・承認・権限判定はすべて API 側で実施(クライアント改ざん不可)

## API 概要

| メソッド/パス | 権限 | 説明 |
|---|---|---|
| `POST /api/auth/register` `login` `logout` | — | 認証 |
| `GET /api/me` | ログイン | 自分の状態(ランク・権限・バッジ) |
| `GET /api/quests` / `POST /api/quests/<id>/complete` | ログイン | クエスト一覧・完了 |
| `POST /api/quests` | `create_quests` | クエスト作成 |
| `GET /api/contents` | ログイン | コンテンツ(ツール/記事/動画)一覧 |
| `POST /api/contents` / `PATCH /api/contents/<id>` | `manage_contents` | コンテンツ登録・編集・アーカイブ(対応クエスト自動生成) |
| `GET/POST /api/proposals` | ログイン | 改善提案の閲覧・投稿 |
| `POST /api/proposals/<id>/review` | `approve_proposals` | 採用/見送り |
| `GET /api/shop` / `POST /api/shop/<id>/redeem` | ログイン | ショップ |
| `GET /api/leaderboard` / `GET /api/activity` | ログイン | ランキング・自分の履歴 |
| `POST /api/users/<id>/praise` | `mentor` | 称賛ボーナス |
| `GET /api/admin/users` `stats` / `POST /api/admin/users/<id>/role` | admin | メンバー管理・統計 |
| `GET/PATCH /api/admin/quests(/<id>)` | admin | クエストの報酬調整・有効/無効化 |
| `GET/POST/PATCH /api/admin/shop(/<id>)` | admin | ショップアイテムの追加・価格調整・停止 |

## コンテンツ管理(記事・ツール・動画)

管理者およびプラチナ到達者(`manage_contents` 権限)は、社内ツール・記事・動画を
LIBRARY セクションから登録できます。

- 登録時に**対応クエストを自動生成**(ツール→「〜を使ってみる」24h繰り返し、記事/動画→「〜を読了/視聴する」1回限り。EXP/pt は上書き可能)
- コンテンツをアーカイブすると連動クエストも自動停止、再公開で復活
- クエストカードにはコンテンツへのリンクが表示され、メンバーは「開く→取り組む→完了報告」の動線で回遊できます

## 本番運用メモ

- `flask run` の開発サーバーではなく gunicorn 等の WSGI サーバーで起動してください:
  `gunicorn 'backend:create_app()'`
- SQLite は同時書き込みが少ない社内規模(〜数百人)なら十分。超える場合は PostgreSQL への移行を検討
- リバースプロキシ(HTTPS)配下では Cookie に `Secure` 属性の追加を推奨
