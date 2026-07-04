"""API 統合テスト: python3 -m unittest discover tests"""
import os
import sqlite3
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import create_app  # noqa: E402


class ApiTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(self.db_path)
        self.app = create_app({"DATABASE": self.db_path, "ADMIN_PASSWORD": "adminpass123", "TESTING": True})

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def client(self):
        return self.app.test_client()

    def register(self, c, name="tanaka", password="password123"):
        return c.post("/api/auth/register", json={"name": name, "password": password})

    # ---- 認証 ----

    def test_register_login_me(self):
        c = self.client()
        res = self.register(c)
        self.assertEqual(res.status_code, 200)
        me = c.get("/api/me").get_json()
        self.assertEqual(me["name"], "tanaka")
        self.assertEqual(me["exp"], 0)
        self.assertEqual(me["rank"]["current"]["key"], "bronze")

        c2 = self.client()
        self.assertEqual(c2.get("/api/me").status_code, 401)
        res = c2.post("/api/auth/login", json={"name": "tanaka", "password": "wrong"})
        self.assertEqual(res.status_code, 401)
        res = c2.post("/api/auth/login", json={"name": "tanaka", "password": "password123"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(c2.get("/api/me").get_json()["name"], "tanaka")

    def test_register_validation(self):
        c = self.client()
        self.assertEqual(self.register(c, name="", password="password123").status_code, 400)
        self.assertEqual(self.register(c, name="a", password="short").status_code, 400)
        self.register(c, name="dup")
        self.assertEqual(self.register(self.client(), name="dup").status_code, 409)

    # ---- クエスト ----

    def test_quest_completion_and_onetime_guard(self):
        c = self.client()
        self.register(c)
        res = c.post("/api/quests/q_quiz/complete")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["me"]["exp"], 60)
        self.assertEqual(data["me"]["points"], 15)
        # 1回限りクエストの再実行は 409
        self.assertEqual(c.post("/api/quests/q_quiz/complete").status_code, 409)
        # クールダウン付きクエストは連続実行で 429
        self.assertEqual(c.post("/api/quests/q_use_tool/complete").status_code, 200)
        self.assertEqual(c.post("/api/quests/q_use_tool/complete").status_code, 429)

    def test_rank_up_flag(self):
        c = self.client()
        self.register(c)
        c.post("/api/quests/q_quiz/complete")    # 60
        c.post("/api/quests/q_share/complete")   # +70 = 130
        res = c.post("/api/quests/q_workshop/complete")  # +80 = 210 → silver
        data = res.get_json()
        self.assertTrue(data["rank_up"])
        self.assertEqual(data["me"]["rank"]["current"]["key"], "silver")
        self.assertIn("buy_boost", data["me"]["permissions"])

    # ---- 提案と権限 ----

    def test_proposal_flow_and_permissions(self):
        c1 = self.client()
        self.register(c1, name="author")
        res = c1.post("/api/proposals", json={"text": "入力欄にサンプル値を表示したい"})
        self.assertEqual(res.status_code, 201)
        me1 = res.get_json()["me"]
        self.assertEqual(me1["exp"], 100)
        pid = c1.get("/api/proposals").get_json()["proposals"][0]["id"]

        # ブロンズの他ユーザーは承認権限なし → 403
        c2 = self.client()
        self.register(c2, name="reviewer")
        res = c2.post(f"/api/proposals/{pid}/review", json={"decision": "approved"})
        self.assertEqual(res.status_code, 403)

        # admin は承認できる
        ca = self.client()
        ca.post("/api/auth/login", json={"name": "admin", "password": "adminpass123"})
        # 自分の提案は承認不可のチェック: author 自身が gold でも不可(まず admin で正常系)
        res = ca.post(f"/api/proposals/{pid}/review", json={"decision": "approved"})
        self.assertEqual(res.status_code, 200)
        # 投稿者に採用ボーナスが入る
        me1 = c1.get("/api/me").get_json()
        self.assertEqual(me1["exp"], 100 + 180)
        self.assertEqual(me1["points"], 30 + 60)
        # 二重審査は 409
        res = ca.post(f"/api/proposals/{pid}/review", json={"decision": "rejected"})
        self.assertEqual(res.status_code, 409)

    def test_cannot_review_own_proposal(self):
        ca = self.client()
        ca.post("/api/auth/login", json={"name": "admin", "password": "adminpass123"})
        ca.post("/api/proposals", json={"text": "自作自演テスト"})
        pid = ca.get("/api/proposals").get_json()["proposals"][0]["id"]
        res = ca.post(f"/api/proposals/{pid}/review", json={"decision": "approved"})
        self.assertEqual(res.status_code, 403)

    # ---- ショップ ----

    def test_shop_redeem_and_permission_purchase(self):
        c = self.client()
        self.register(c)
        # ポイント不足
        self.assertEqual(c.post("/api/shop/s_seat/redeem").status_code, 400)
        # 提案を5回投稿して 150pt 貯める
        for i in range(5):
            c.post("/api/proposals", json={"text": f"提案 {i}"})
        me = c.get("/api/me").get_json()
        self.assertEqual(me["points"], 150)
        self.assertNotIn("approve_proposals", me["permissions"])
        # 承認権限をポイント購入
        res = c.post("/api/shop/s_approver/redeem")
        self.assertEqual(res.status_code, 200)
        me = res.get_json()["me"]
        self.assertEqual(me["points"], 0)
        self.assertIn("approve_proposals", me["permissions"])
        # 非繰り返しアイテムの再購入は 409(ポイントがあっても)
        for i in range(5):
            c.post("/api/proposals", json={"text": f"追加提案 {i}"})
        self.assertEqual(c.post("/api/shop/s_approver/redeem").status_code, 409)

    def test_boost_requires_silver_and_multiplies_exp(self):
        c = self.client()
        self.register(c)
        # ブロンズでは購入不可
        for i in range(3):
            c.post("/api/proposals", json={"text": f"p{i}"})  # 300exp(silver) / 90pt
        me = c.get("/api/me").get_json()
        self.assertIn("buy_boost", me["permissions"])
        res = c.post("/api/shop/s_boost/redeem")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["me"]["boost_charges"], 5)
        # ブースト適用で 60 → 90 EXP
        res = c.post("/api/quests/q_quiz/complete")
        data = res.get_json()
        self.assertTrue(data["awarded"]["boosted"])
        self.assertEqual(data["awarded"]["exp"], 90)
        self.assertEqual(data["me"]["boost_charges"], 4)

    # ---- 管理者 ----

    def test_admin_endpoints(self):
        c = self.client()
        self.register(c)
        self.assertEqual(c.get("/api/admin/users").status_code, 403)
        ca = self.client()
        ca.post("/api/auth/login", json={"name": "admin", "password": "adminpass123"})
        users = ca.get("/api/admin/users").get_json()["users"]
        self.assertTrue(any(u["name"] == "tanaka" for u in users))
        stats = ca.get("/api/admin/stats").get_json()
        self.assertEqual(stats["users"], 1)
        uid = next(u["id"] for u in users if u["name"] == "tanaka")
        res = ca.post(f"/api/admin/users/{uid}/role", json={"role": "admin"})
        self.assertEqual(res.status_code, 200)
        # 昇格後は管理エンドポイントにアクセスできる
        self.assertEqual(c.get("/api/admin/users").status_code, 200)

    # ---- クエスト作成権限 ----

    def test_quest_creation_requires_platinum(self):
        c = self.client()
        self.register(c)
        res = c.post("/api/quests", json={"title": "t", "description": "d", "exp": 50, "pts": 10, "category": "usage"})
        self.assertEqual(res.status_code, 403)
        ca = self.client()
        ca.post("/api/auth/login", json={"name": "admin", "password": "adminpass123"})
        res = ca.post("/api/quests", json={"title": "新クエスト", "description": "テスト", "exp": 50, "pts": 10, "category": "usage"})
        self.assertEqual(res.status_code, 201)
        quests = c.get("/api/quests").get_json()["quests"]
        self.assertTrue(any(q["title"] == "新クエスト" for q in quests))

    # ---- コンテンツ管理 ----

    def test_content_requires_permission(self):
        c = self.client()
        self.register(c)
        res = c.post("/api/contents", json={"title": "社内BIツール", "type": "tool"})
        self.assertEqual(res.status_code, 403)
        # 一覧は誰でも見られる(管理フラグは False)
        data = c.get("/api/contents").get_json()
        self.assertFalse(data["can_manage"])

    def test_content_crud_and_auto_quest(self):
        ca = self.client()
        ca.post("/api/auth/login", json={"name": "admin", "password": "adminpass123"})
        res = ca.post("/api/contents", json={
            "title": "売上ダッシュボード", "type": "tool",
            "url": "https://example.com/dash", "description": "売上を可視化するBIツール",
        })
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertIsNotNone(data["quest_id"])

        # 自動生成クエストが一般ユーザーにも見え、コンテンツ情報が付く
        c = self.client()
        self.register(c)
        quests = c.get("/api/quests").get_json()["quests"]
        auto = next(q for q in quests if q["id"] == data["quest_id"])
        self.assertIn("売上ダッシュボード", auto["title"])
        self.assertEqual(auto["content_url"], "https://example.com/dash")
        self.assertEqual(auto["exp"], 30)  # tool の既定値
        # 完了もできる
        self.assertEqual(c.post(f"/api/quests/{auto['id']}/complete").status_code, 200)

        # アーカイブすると連動クエストも止まる
        res = ca.patch(f"/api/contents/{data['id']}", json={"active": False})
        self.assertEqual(res.status_code, 200)
        quests = c.get("/api/quests").get_json()["quests"]
        self.assertFalse(any(q["id"] == data["quest_id"] for q in quests))

    def test_content_validation(self):
        ca = self.client()
        ca.post("/api/auth/login", json={"name": "admin", "password": "adminpass123"})
        self.assertEqual(ca.post("/api/contents", json={"title": "", "type": "tool"}).status_code, 400)
        self.assertEqual(ca.post("/api/contents", json={"title": "t", "type": "bad"}).status_code, 400)
        self.assertEqual(
            ca.post("/api/contents", json={"title": "t", "type": "tool", "url": "javascript:alert(1)"}).status_code, 400)

    # ---- クエスト/ショップ管理 ----

    def test_admin_quest_edit_and_disable(self):
        ca = self.client()
        ca.post("/api/auth/login", json={"name": "admin", "password": "adminpass123"})
        res = ca.patch("/api/admin/quests/q_quiz", json={"exp": 100, "pts": 20})
        self.assertEqual(res.status_code, 200)
        c = self.client()
        self.register(c)
        data = c.post("/api/quests/q_quiz/complete").get_json()
        self.assertEqual(data["awarded"]["exp"], 100)
        # 無効化すると一覧から消え、完了もできない
        ca.patch("/api/admin/quests/q_use_tool", json={"active": False})
        quests = c.get("/api/quests").get_json()["quests"]
        self.assertFalse(any(q["id"] == "q_use_tool" for q in quests))
        self.assertEqual(c.post("/api/quests/q_use_tool/complete").status_code, 404)
        # 一般ユーザーは管理APIに触れない
        self.assertEqual(c.patch("/api/admin/quests/q_quiz", json={"exp": 1}).status_code, 403)

    def test_admin_shop_add_and_edit(self):
        ca = self.client()
        ca.post("/api/auth/login", json={"name": "admin", "password": "adminpass123"})
        res = ca.post("/api/admin/shop", json={"title": "ランチ券", "description": "作者とランチ", "cost": 100})
        self.assertEqual(res.status_code, 201)
        item_id = res.get_json()["id"]
        # 一般ユーザーのショップ一覧に出る
        c = self.client()
        self.register(c)
        items = c.get("/api/shop").get_json()["items"]
        self.assertTrue(any(i["id"] == item_id for i in items))
        # 価格変更と停止
        self.assertEqual(ca.patch(f"/api/admin/shop/{item_id}", json={"cost": 80}).status_code, 200)
        self.assertEqual(ca.patch(f"/api/admin/shop/{item_id}", json={"active": False}).status_code, 200)
        items = c.get("/api/shop").get_json()["items"]
        self.assertFalse(any(i["id"] == item_id for i in items))

    # ---- 競合・整合性(レビュー指摘の回帰テスト) ----

    def _set_user(self, name, **cols):
        db = sqlite3.connect(self.db_path)
        sets = ", ".join(f"{k} = ?" for k in cols)
        db.execute(f"UPDATE users SET {sets} WHERE name = ?", (*cols.values(), name))
        db.commit()
        db.close()

    def test_boost_charges_never_negative(self):
        c = self.client()
        self.register(c)
        self._set_user("tanaka", boost_charges=1)
        r1 = c.post("/api/quests/q_quiz/complete").get_json()
        self.assertTrue(r1["awarded"]["boosted"])
        r2 = c.post("/api/quests/q_share/complete").get_json()
        self.assertFalse(r2["awarded"]["boosted"])  # 残数0では適用されない
        self.assertEqual(r2["me"]["boost_charges"], 0)  # マイナスにならない

    def test_concurrent_redeem_no_double_spend(self):
        c = self.client()
        self.register(c)
        self._set_user("tanaka", points=150)
        results = []
        barrier = threading.Barrier(2)

        def buy():
            cc = self.client()
            cc.post("/api/auth/login", json={"name": "tanaka", "password": "password123"})
            barrier.wait()
            results.append(cc.post("/api/shop/s_approver/redeem").status_code)

        threads = [threading.Thread(target=buy) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # 片方だけ成功し、残高はマイナスにならず、交換記録も1件のみ
        self.assertEqual(sorted(results)[0], 200)
        self.assertIn(sorted(results)[1], (400, 409))
        db = sqlite3.connect(self.db_path)
        points = db.execute("SELECT points FROM users WHERE name='tanaka'").fetchone()[0]
        n = db.execute("SELECT COUNT(*) FROM redemptions").fetchone()[0]
        db.close()
        self.assertEqual(points, 0)
        self.assertEqual(n, 1)

    def test_archived_content_quest_hidden_but_admin_disable_preserved(self):
        ca = self.client()
        ca.post("/api/auth/login", json={"name": "admin", "password": "adminpass123"})
        res = ca.post("/api/contents", json={"title": "BIツール", "type": "tool"}).get_json()
        cid, qid = res["id"], res["quest_id"]
        # 管理者がクエストを個別に無効化
        ca.patch(f"/api/admin/quests/{qid}", json={"active": False})
        # コンテンツをアーカイブ → 再公開しても、無効化したクエストは復活しない
        ca.patch(f"/api/contents/{cid}", json={"active": False})
        ca.patch(f"/api/contents/{cid}", json={"active": True})
        c = self.client()
        self.register(c)
        quests = c.get("/api/quests").get_json()["quests"]
        self.assertFalse(any(q["id"] == qid for q in quests))
        # アーカイブ中は完了APIも拒否される
        ca.patch(f"/api/admin/quests/{qid}", json={"active": True})
        ca.patch(f"/api/contents/{cid}", json={"active": False})
        self.assertEqual(c.post(f"/api/quests/{qid}/complete").status_code, 404)

    def test_content_title_edit_syncs_quest_title(self):
        ca = self.client()
        ca.post("/api/auth/login", json={"name": "admin", "password": "adminpass123"})
        res = ca.post("/api/contents", json={"title": "旧タイトル", "type": "article"}).get_json()
        ca.patch(f"/api/contents/{res['id']}", json={"title": "新タイトル"})
        c = self.client()
        self.register(c)
        quest = next(q for q in c.get("/api/quests").get_json()["quests"] if q["id"] == res["quest_id"])
        self.assertEqual(quest["title"], "「新タイトル」を読了する")

    def test_meta_includes_rank_permissions(self):
        data = self.client().get("/api/meta").get_json()
        self.assertIn("manage_contents", data["rank_permissions"]["platinum"])

    def test_review_returns_rank_up_flag(self):
        c = self.client()
        self.register(c)
        c.post("/api/proposals", json={"text": "テスト提案"})
        pid = c.get("/api/proposals").get_json()["proposals"][0]["id"]
        ca = self.client()
        ca.post("/api/auth/login", json={"name": "admin", "password": "adminpass123"})
        res = ca.post(f"/api/proposals/{pid}/review", json={"decision": "approved"}).get_json()
        self.assertIn("rank_up", res)

    # ---- アカウント管理(UX改善) ----

    def test_change_own_password(self):
        c = self.client()
        self.register(c)
        res = c.post("/api/auth/password", json={"current_password": "wrong", "new_password": "newpassword1"})
        self.assertEqual(res.status_code, 403)
        res = c.post("/api/auth/password", json={"current_password": "password123", "new_password": "short"})
        self.assertEqual(res.status_code, 400)
        res = c.post("/api/auth/password", json={"current_password": "password123", "new_password": "newpassword1"})
        self.assertEqual(res.status_code, 200)
        c2 = self.client()
        self.assertEqual(c2.post("/api/auth/login", json={"name": "tanaka", "password": "newpassword1"}).status_code, 200)

    def test_admin_reset_password_invalidates_sessions(self):
        c = self.client()
        self.register(c)
        ca = self.client()
        ca.post("/api/auth/login", json={"name": "admin", "password": "adminpass123"})
        uid = next(u["id"] for u in ca.get("/api/admin/users").get_json()["users"] if u["name"] == "tanaka")
        res = ca.post(f"/api/admin/users/{uid}/password", json={"password": "resetpass99"})
        self.assertEqual(res.status_code, 200)
        # 旧セッションは無効化され、新パスワードでログインできる
        self.assertEqual(c.get("/api/me").status_code, 401)
        c2 = self.client()
        self.assertEqual(c2.post("/api/auth/login", json={"name": "tanaka", "password": "resetpass99"}).status_code, 200)

    def test_rename(self):
        c = self.client()
        self.register(c)
        c2 = self.client()
        self.register(c2, name="sato")
        res = c.patch("/api/auth/profile", json={"name": "sato"})
        self.assertEqual(res.status_code, 409)
        res = c.patch("/api/auth/profile", json={"name": "tanaka2"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(c.get("/api/me").get_json()["name"], "tanaka2")

    # ---- 提案の編集・取り下げ ----

    def test_proposal_edit_rules(self):
        c = self.client()
        self.register(c)
        c.post("/api/proposals", json={"text": "誤字あり提案"})
        pid = c.get("/api/proposals").get_json()["proposals"][0]["id"]
        # 本人・審査前は編集可
        self.assertEqual(c.patch(f"/api/proposals/{pid}", json={"text": "修正済み提案"}).status_code, 200)
        # 他人は編集不可
        c2 = self.client()
        self.register(c2, name="other")
        self.assertEqual(c2.patch(f"/api/proposals/{pid}", json={"text": "改ざん"}).status_code, 403)
        # 審査後は編集不可
        ca = self.client()
        ca.post("/api/auth/login", json={"name": "admin", "password": "adminpass123"})
        ca.post(f"/api/proposals/{pid}/review", json={"decision": "approved"})
        self.assertEqual(c.patch(f"/api/proposals/{pid}", json={"text": "後から変更"}).status_code, 409)

    def test_proposal_withdraw_claws_back_reward(self):
        c = self.client()
        self.register(c)
        c.post("/api/proposals", json={"text": "取り下げる提案"})
        me = c.get("/api/me").get_json()
        self.assertEqual((me["exp"], me["points"]), (100, 30))
        pid = c.get("/api/proposals").get_json()["proposals"][0]["id"]
        res = c.delete(f"/api/proposals/{pid}")
        self.assertEqual(res.status_code, 200)
        me = res.get_json()["me"]
        self.assertEqual((me["exp"], me["points"]), (0, 0))
        self.assertEqual(len(c.get("/api/proposals").get_json()["proposals"]), 0)
        # ポイントを使い切っていても残高はマイナスにならない
        c.post("/api/proposals", json={"text": "2件目"})
        self._set_user("tanaka", points=5)  # 30pt中25pt使用済みの想定
        pid = c.get("/api/proposals").get_json()["proposals"][0]["id"]
        me = c.delete(f"/api/proposals/{pid}").get_json()["me"]
        self.assertEqual(me["points"], 0)

    def test_shop_includes_redeem_note(self):
        c = self.client()
        self.register(c)
        items = c.get("/api/shop").get_json()["items"]
        qa = next(i for i in items if i["id"] == "s_qa")
        self.assertIn("日程", qa["redeem_note"])

    # ---- リーダーボード ----

    def test_leaderboard_excludes_admin(self):
        c = self.client()
        self.register(c)
        c.post("/api/quests/q_quiz/complete")
        rows = c.get("/api/leaderboard").get_json()["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "tanaka")
        self.assertTrue(rows[0]["me"])


if __name__ == "__main__":
    unittest.main()
