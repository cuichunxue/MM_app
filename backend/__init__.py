"""LEVEL UP LAB — Flask アプリケーションファクトリ。"""
import os

from flask import Flask, send_from_directory


def create_app(test_config: dict = None) -> Flask:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app = Flask(
        __name__,
        static_folder=os.path.join(root, "static"),
        static_url_path="/static",
        instance_path=os.path.join(root, "instance"),
    )
    app.config.from_mapping(
        DATABASE=os.environ.get("DATABASE", os.path.join(app.instance_path, "levelup.db")),
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", "admin1234"),
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev"),
    )
    if test_config:
        app.config.update(test_config)

    from . import db
    db.init_db(app)
    app.teardown_appcontext(db.close_db)

    from . import auth, routes
    app.register_blueprint(auth.bp)
    app.register_blueprint(routes.bp)

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    return app
