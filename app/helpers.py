from datetime import date, timedelta
from functools import wraps

from flask import flash, redirect, request, session, url_for

from .db import get_db


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        if session.get("role") != "admin":
            flash("该操作需要管理员权限", "error")
            return redirect(url_for("views.today"))
        return f(*args, **kwargs)

    return wrapper


def parse_iso(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def week_bounds(d: date):
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=6)


def current_child():
    db = get_db()
    children = db.execute("SELECT * FROM children WHERE active = 1 ORDER BY id").fetchall()
    if not children:
        return None, children
    cid = request.args.get("child", type=int) or session.get("child_id")
    child = next((c for c in children if c["id"] == cid), None) or children[0]
    session["child_id"] = child["id"]
    return child, children


def balance_of(child_id) -> float:
    row = get_db().execute(
        """SELECT c.initial_balance + COALESCE(
               (SELECT SUM(income - expense) FROM ledger l WHERE l.child_id = c.id), 0
           ) AS bal
           FROM children c WHERE c.id = ?""",
        (child_id,),
    ).fetchone()
    return round(float(row["bal"]), 2) if row else 0.0


def day_score(db, child_id, d: date):
    row = db.execute(
        """SELECT COUNT(*) AS cnt, COALESCE(SUM(t.value), 0) AS total
           FROM checkins ck
           JOIN tasks t ON t.id = ck.task_id
           WHERE ck.child_id = ? AND ck.date = ?""",
        (child_id, d.isoformat()),
    ).fetchone()
    return int(row["cnt"]), float(row["total"])


def sync_daily(db, child_id, d: date):
    cnt, total = day_score(db, child_id, d)
    ds = d.isoformat()
    row = db.execute(
        "SELECT id FROM ledger WHERE child_id = ? AND date = ? AND source = 'daily'",
        (child_id, ds),
    ).fetchone()
    if cnt:
        reason = f"每日得分（完成 {cnt} 项）"
        if row:
            db.execute(
                "UPDATE ledger SET income = ?, reason = ? WHERE id = ?",
                (total, reason, row["id"]),
            )
        else:
            db.execute(
                "INSERT INTO ledger(child_id, date, reason, income, source) "
                "VALUES(?, ?, ?, ?, 'daily')",
                (child_id, ds, reason, total),
            )
    elif row:
        db.execute("DELETE FROM ledger WHERE id = ?", (row["id"],))


def resync_all_daily(db):
    pairs = db.execute("SELECT DISTINCT child_id, date FROM checkins").fetchall()
    for p in pairs:
        d = parse_iso(p["date"])
        if d:
            sync_daily(db, p["child_id"], d)


def settlement(db, child_id, mon: date, sun: date) -> dict:
    row = db.execute(
        """SELECT COALESCE(SUM(income), 0) AS inc, COALESCE(SUM(expense), 0) AS exp
           FROM ledger
           WHERE child_id = ? AND date BETWEEN ? AND ?""",
        (child_id, mon.isoformat(), sun.isoformat()),
    ).fetchone()
    earned = float(row["inc"])
    spent = float(row["exp"])
    now = balance_of(child_id)
    opening = round(now - earned + spent, 2)
    return {
        "opening": opening,
        "earned": round(earned, 2),
        "available": round(opening + earned, 2),
        "spent": round(spent, 2),
        "carry": now,
    }
