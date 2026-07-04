"""API 統合テスト: python3 -m unittest discover tests"""
import os
import sys
import tempfile
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
