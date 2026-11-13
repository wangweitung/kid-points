from datetime import date, datetime, timedelta, timezone
from functools import wraps
import math

from flask import flash, g, redirect, request, session, url_for

from .db import get_db

# All business dates must be Beijing time, independent of server/container TZ.
APP_TZ = timezone(timedelta(hours=8))


def local_today() -> date:
    return datetime.now(APP_TZ).date()


def parse_amount(value, default: float = 0.0) -> float:
    """Parse a form value into a finite float; NaN/Inf/invalid fall back to default."""
    try:
        f = float(value or default)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


def session_user():
    """Validate the session against the DB; refresh role, invalidate stale sessions.

    Returns the users row, or None when logged out / deleted / password-reset.
    Cached per request in g.
    """
    if hasattr(g, "_session_user"):
        return g._session_user
    user = None
    uid = session.get("user_id")
    if uid is not None:
        row = get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if row is None:
            session.clear()
            flash("账号已不存在，请重新登录", "error")
        elif session.get("session_ver") != row["session_ver"]:
            session.clear()
            flash("登录已失效，请重新登录", "error")
        else:
            session["role"] = row["role"]
            user = row
    g._session_user = user
    return user


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session_user() is None:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = session_user()
        if user is None:
            return redirect(url_for("auth.login"))
        if user["role"] != "admin":
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
           JOIN tasks t ON t.id = ck.task_id AND t.active = 1
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
    """Week settlement scoped to the given week, so past weeks stay correct."""
    row = db.execute(
        """SELECT COALESCE(SUM(income), 0) AS inc, COALESCE(SUM(expense), 0) AS exp
           FROM ledger
           WHERE child_id = ? AND date BETWEEN ? AND ?""",
        (child_id, mon.isoformat(), sun.isoformat()),
    ).fetchone()
    earned = float(row["inc"])
    spent = float(row["exp"])
    base = db.execute(
        """SELECT c.initial_balance + COALESCE(
               (SELECT SUM(income - expense) FROM ledger l
                WHERE l.child_id = c.id AND l.date < ?), 0
           ) AS bal
           FROM children c WHERE c.id = ?""",
        (mon.isoformat(), child_id),
    ).fetchone()
    opening = round(float(base["bal"]), 2) if base else 0.0
    return {
        "opening": opening,
        "earned": round(earned, 2),
        "available": round(opening + earned, 2),
        "spent": round(spent, 2),
        "carry": round(opening + earned - spent, 2),
    }
