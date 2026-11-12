from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import generate_password_hash

from .db import get_db, get_setting, set_setting
from .helpers import admin_required, resync_all_daily

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.get("/")
@admin_required
def panel():
    db = get_db()
    return render_template(
        "admin.html",
        tasks=db.execute("SELECT * FROM tasks ORDER BY active DESC, sort_order, id").fetchall(),
        children=db.execute("SELECT * FROM children ORDER BY id").fetchall(),
        users=db.execute("SELECT * FROM users ORDER BY id").fetchall(),
        registration_open=get_setting("registration_open") == "1",
        today_label=None,
    )


@bp.post("/registration")
@admin_required
def registration():
    open_now = request.form.get("open") == "1"
    set_setting("registration_open", "1" if open_now else "0")
    flash("注册已开启" if open_now else "注册已关闭", "ok")
    return redirect(url_for("admin.panel"))


@bp.post("/task/add")
@admin_required
def task_add():
    name = (request.form.get("name") or "").strip()
    try:
        value = float(request.form.get("value") or 0)
    except ValueError:
        value = 0
    if not name or value <= 0:
        flash("请填写任务名称和正数分值", "error")
    else:
        db = get_db()
        db.execute(
            "INSERT INTO tasks(name, value, sort_order) VALUES(?, ?, "
            "(SELECT COALESCE(MAX(sort_order), 0) + 1 FROM tasks))",
            (name, value),
        )
        db.commit()
        flash("已添加任务", "ok")
    return redirect(url_for("admin.panel"))


@bp.post("/task/update")
@admin_required
def task_update():
    task_id = request.form.get("id", type=int)
    name = (request.form.get("name") or "").strip()
    try:
        value = float(request.form.get("value") or 0)
    except ValueError:
        value = 0
    db = get_db()
    if not task_id or not name or value <= 0:
        flash("名称和分值必须有效", "error")
    else:
        db.execute(
            "UPDATE tasks SET name = ?, value = ? WHERE id = ?", (name, value, task_id)
        )
        resync_all_daily(db)
        db.commit()
        flash("已更新，历史每日得分已按新分值重算", "ok")
    return redirect(url_for("admin.panel"))


@bp.post("/task/toggle")
@admin_required
def task_toggle():
    db = get_db()
    db.execute(
        "UPDATE tasks SET active = 1 - active WHERE id = ?",
        (request.form.get("id", type=int) or -1,),
    )
    db.commit()
    flash("已更新任务状态", "ok")
    return redirect(url_for("admin.panel"))


@bp.post("/child/add")
@admin_required
def child_add():
    name = (request.form.get("name") or "").strip()
    try:
        initial = float(request.form.get("initial_balance") or 0)
    except ValueError:
        initial = 0
    if not name:
        flash("请填写小朋友姓名", "error")
    else:
        db = get_db()
        db.execute(
            "INSERT INTO children(name, initial_balance) VALUES(?, ?)", (name, initial)
        )
        db.commit()
        flash("已添加", "ok")
    return redirect(url_for("admin.panel"))


@bp.post("/child/update")
@admin_required
def child_update():
    child_id = request.form.get("id", type=int)
    name = (request.form.get("name") or "").strip()
    try:
        initial = float(request.form.get("initial_balance") or 0)
    except ValueError:
        initial = 0
    active = 1 if request.form.get("active") == "1" else 0
    db = get_db()
    if not child_id or not name:
        flash("姓名不能为空", "error")
    else:
        others = db.execute(
            "SELECT COUNT(*) AS c FROM children WHERE active = 1 AND id != ?",
            (child_id,),
        ).fetchone()["c"]
        if not active and others == 0:
            flash("至少保留一个启用中的小朋友", "error")
        else:
            db.execute(
                "UPDATE children SET name = ?, initial_balance = ?, active = ? WHERE id = ?",
                (name, initial, active, child_id),
            )
            db.commit()
            flash("已更新", "ok")
    return redirect(url_for("admin.panel"))


def _other_admins_exist(db, exclude_id) -> bool:
    return (
        db.execute(
            "SELECT 1 FROM users WHERE role = 'admin' AND id != ? LIMIT 1",
            (exclude_id,),
        ).fetchone()
        is not None
    )


@bp.post("/user/update")
@admin_required
def user_update():
    user_id = request.form.get("id", type=int)
    role = request.form.get("role")
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row or role not in ("admin", "user"):
        flash("参数错误", "error")
    elif row["role"] == "admin" and role != "admin" and not _other_admins_exist(db, user_id):
        flash("不能降级最后一个管理员", "error")
    else:
        db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        db.commit()
        flash("已更新用户角色", "ok")
    return redirect(url_for("admin.panel"))


@bp.post("/user/password")
@admin_required
def user_password():
    user_id = request.form.get("id", type=int)
    password = request.form.get("password") or ""
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        flash("用户不存在", "error")
    elif len(password) < 4:
        flash("密码至少 4 位", "error")
    else:
        db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(password), user_id),
        )
        db.commit()
        flash(f"已重置 {row['username']} 的密码", "ok")
    return redirect(url_for("admin.panel"))


@bp.post("/user/delete")
@admin_required
def user_delete():
    user_id = request.form.get("id", type=int)
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        flash("用户不存在", "error")
    elif user_id == session["user_id"]:
        flash("不能删除自己", "error")
    elif row["role"] == "admin" and not _other_admins_exist(db, user_id):
        flash("不能删除最后一个管理员", "error")
    else:
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        db.commit()
        flash(f"已删除用户 {row['username']}", "ok")
    return redirect(url_for("admin.panel"))
