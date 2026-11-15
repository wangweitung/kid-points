import math
import secrets
from pathlib import Path

from flask import Flask, flash, redirect, request, session, url_for
from flask_wtf import CSRFProtect

from . import db
from .helpers import session_user

csrf = CSRFProtect()


def _secret_key(data_dir: Path) -> str:
    import os

    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    path = data_dir / "secret_key"
    if not path.exists():
        path.write_text(secrets.token_hex(32), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path.read_text(encoding="utf-8")


def _fmt_filter(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return value
    if not math.isfinite(f):
        return value
    if f == int(f):
        return f"{int(f):,}"
    return f"{f:,.2f}".rstrip("0").rstrip(".")


def create_app() -> Flask:
    data_dir = db.data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    app = Flask(__name__)
    app.config["SECRET_KEY"] = _secret_key(data_dir)
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["WTF_CSRF_TIME_LIMIT"] = None
    # 静态资源长缓存：no-cache 会让手机端每次刷新都回源校验 CSS，
    # 弱网下浏览器先把未加样式的 HTML 画出来（闪一下简陋页面）。
    # 配合模板里的 mtime 版本号，文件更新后缓存自动失效。
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 30 * 24 * 3600

    _asset_cache: dict = {}

    @app.context_processor
    def _assets():
        def asset_url(filename: str) -> str:
            path = Path(app.static_folder) / filename
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0
            cached = _asset_cache.get(filename)
            if cached is None or cached[0] != mtime:
                url = url_for("static", filename=filename, v=int(mtime))
                _asset_cache[filename] = (mtime, url)
            return _asset_cache[filename][1]

        return {"asset_url": asset_url}

    csrf.init_app(app)
    db.init_app(app)
    app.jinja_env.filters["fmt"] = _fmt_filter

    from .admin import bp as admin_bp
    from .auth import bp as auth_bp
    from .views import bp as views_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(admin_bp)

    @app.get("/healthz")
    def healthz():
        return "ok"

    @app.before_request
    def _guard():
        ep = request.endpoint
        if ep in (None, "static", "healthz"):
            return
        if not db.has_users():
            if ep != "auth.setup":
                return redirect(url_for("auth.setup"))
            return
        if ep == "auth.setup":
            return redirect(url_for("auth.login"))
        if ep in ("auth.login", "auth.register"):
            if session_user() is not None:
                return redirect(url_for("views.today"))
            if ep == "auth.register" and db.get_setting("registration_open") != "1":
                flash("注册已关闭，请联系管理员", "error")
                return redirect(url_for("auth.login"))
            return
        if session_user() is None:
            return redirect(url_for("auth.login"))

    with app.app_context():
        db.ensure_schema()

    return app
