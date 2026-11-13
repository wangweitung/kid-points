from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db, get_setting, has_users

bp = Blueprint("auth", __name__, url_prefix="/auth")


def _create_user(username, password, role):
    db = get_db()
    db.execute(
        "INSERT INTO users(username, password_hash, role) VALUES(?, ?, ?)",
        (username, generate_password_hash(password), role),
    )
    db.commit()


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    if has_users():
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        errors = []
        if not username:
            errors.append("请输入用户名")
        if len(password) < 4:
            errors.append("密码至少 4 位")
        if password != confirm:
            errors.append("两次输入的密码不一致")
        if not errors:
            _create_user(username, password, "admin")
            flash("管理员创建成功，请登录", "ok")
            return redirect(url_for("auth.login"))
        for e in errors:
            flash(e, "error")
        return render_template("setup.html", username=username)
    return render_template("setup.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        row = get_db().execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            session.clear()
            session["user_id"] = row["id"]
            session["username"] = row["username"]
            session["role"] = row["role"]
            session["session_ver"] = row["session_ver"]
            return redirect(url_for("views.today"))
        flash("用户名或密码错误", "error")
        return render_template("login.html", username=username,
                              registration_open=get_setting("registration_open") == "1")
    return render_template("login.html",
                           registration_open=get_setting("registration_open") == "1")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if get_setting("registration_open") != "1":
        flash("注册已关闭，请联系管理员", "error")
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        errors = []
        if not username:
            errors.append("请输入用户名")
        if len(password) < 4:
            errors.append("密码至少 4 位")
        if password != confirm:
            errors.append("两次输入的密码不一致")
        if not errors and get_db().execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone():
            errors.append("用户名已存在")
        if not errors:
            _create_user(username, password, "user")
            flash("注册成功，请登录", "ok")
            return redirect(url_for("auth.login"))
        for e in errors:
            flash(e, "error")
        return render_template("register.html", username=username)
    return render_template("register.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
