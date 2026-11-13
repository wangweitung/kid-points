import calendar
from datetime import date, timedelta

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .db import get_db
from .helpers import (
    admin_required,
    balance_of,
    current_child,
    day_score,
    local_today,
    login_required,
    parse_iso,
    settlement,
    sync_daily,
    week_bounds,
)

bp = Blueprint("views", __name__)

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _need_child():
    child, children = current_child()
    if not child:
        return None, render_template("no_child.html", children=children), children
    return child, None, children


@bp.get("/")
def today():
    child, early, children = _need_child()
    if early:
        return early
    db = get_db()
    tasks = db.execute(
        "SELECT * FROM tasks WHERE active = 1 ORDER BY sort_order, id"
    ).fetchall()
    today_d = local_today()
    done_ids = {
        r["task_id"]
        for r in db.execute(
            "SELECT task_id FROM checkins WHERE child_id = ? AND date = ?",
            (child["id"], today_d.isoformat()),
        )
    }
    task_ids = {t["id"] for t in tasks}
    today_total = sum(t["value"] for t in tasks if t["id"] in done_ids)
    strip = []
    for i in range(6, -1, -1):
        d = today_d - timedelta(days=i)
        cnt, total = day_score(db, child["id"], d)
        strip.append(
            {
                "date": d,
                "wday": "一二三四五六日"[d.weekday()],
                "total": total,
                "count": cnt,
                "is_today": d == today_d,
            }
        )
    return render_template(
        "today.html",
        child=child,
        children=children,
        tasks=tasks,
        done_ids=done_ids,
        today_d=today_d,
        weekday_name=WEEKDAY_NAMES[today_d.weekday()],
        today_total=today_total,
        today_count=len(done_ids & task_ids),
        balance=balance_of(child["id"]),
        strip=strip,
    )


def _tick_state(db, child_id, d: date) -> dict:
    mon, sun = week_bounds(d)
    tasks = db.execute(
        "SELECT id, value FROM tasks WHERE active = 1 ORDER BY sort_order, id"
    ).fetchall()
    task_week = {}
    for t in tasks:
        row = db.execute(
            """SELECT COUNT(*) AS cnt FROM checkins
               WHERE child_id = ? AND task_id = ? AND date BETWEEN ? AND ?""",
            (child_id, t["id"], mon.isoformat(), sun.isoformat()),
        ).fetchone()
        cnt = int(row["cnt"])
        task_week[str(t["id"])] = {"days": cnt, "score": round(cnt * t["value"], 2)}
    day_totals, day_counts = {}, {}
    for i in range(7):
        dd = mon + timedelta(days=i)
        cnt, total = day_score(db, child_id, dd)
        day_totals[dd.isoformat()] = total
        day_counts[dd.isoformat()] = cnt
    t_cnt, t_total = day_score(db, child_id, local_today())
    return {
        "date": d.isoformat(),
        "day_total": day_totals[d.isoformat()],
        "day_count": day_counts[d.isoformat()],
        "task_week": task_week,
        "day_totals": day_totals,
        "day_counts": day_counts,
        "settlement": settlement(db, child_id, mon, sun),
        "balance": balance_of(child_id),
        "today_total": t_total,
        "today_count": t_cnt,
    }


@bp.post("/tick")
@login_required
def tick():
    payload = request.get_json(silent=True) or {}
    child_id = payload.get("child_id")
    task_id = payload.get("task_id")
    d = parse_iso(payload.get("date"))
    if not isinstance(child_id, int) or not isinstance(task_id, int) or d is None:
        return jsonify(error="参数错误"), 400
    if d > local_today():
        return jsonify(error="不能为未来的日期打卡"), 400
    db = get_db()
    child = db.execute(
        "SELECT id FROM children WHERE id = ? AND active = 1", (child_id,)
    ).fetchone()
    task = db.execute(
        "SELECT id FROM tasks WHERE id = ? AND active = 1", (task_id,)
    ).fetchone()
    if not child or not task:
        return jsonify(error="记录不存在"), 404
    ds = d.isoformat()
    existing = db.execute(
        "SELECT id FROM checkins WHERE child_id = ? AND task_id = ? AND date = ?",
        (child_id, task_id, ds),
    ).fetchone()
    if existing:
        db.execute("DELETE FROM checkins WHERE id = ?", (existing["id"],))
        done = False
    else:
        db.execute(
            "INSERT INTO checkins(child_id, task_id, date, created_by) VALUES(?, ?, ?, ?)",
            (child_id, task_id, ds, session["user_id"]),
        )
        done = True
    sync_daily(db, child_id, d)
    db.commit()
    return jsonify(done=done, **_tick_state(db, child_id, d))


@bp.get("/week")
def week():
    child, early, children = _need_child()
    if early:
        return early
    d = parse_iso(request.args.get("date")) or local_today()
    mon, sun = week_bounds(d)
    db = get_db()
    today_d = local_today()
    days = [mon + timedelta(days=i) for i in range(7)]

    tasks = db.execute(
        "SELECT * FROM tasks WHERE active = 1 ORDER BY sort_order, id"
    ).fetchall()
    checked_map = {}
    for r in db.execute(
        """SELECT task_id, date FROM checkins
           WHERE child_id = ? AND date BETWEEN ? AND ?""",
        (child["id"], mon.isoformat(), sun.isoformat()),
    ):
        checked_map.setdefault(r["task_id"], set()).add(r["date"])

    task_rows = []
    for t in tasks:
        checked = [
            (mon + timedelta(days=i)).isoformat() in checked_map.get(t["id"], set())
            for i in range(7)
        ]
        cnt = sum(checked)
        task_rows.append(
            {
                "task": t,
                "checked": checked,
                "days": cnt,
                "score": round(cnt * t["value"], 2) if cnt else None,
            }
        )

    day_totals, day_counts, week_score = [], [], 0.0
    for dd in days:
        cnt, total = day_score(db, child["id"], dd)
        day_counts.append(cnt)
        day_totals.append(total if cnt else None)
        week_score += total

    catalog = db.execute(
        "SELECT * FROM catalog WHERE active = 1 ORDER BY sort_order, id"
    ).fetchall()
    redeemed = {
        r["reason"]
        for r in db.execute(
            """SELECT DISTINCT reason FROM ledger
               WHERE child_id = ? AND source = 'redeem' AND date BETWEEN ? AND ?""",
            (child["id"], mon.isoformat(), sun.isoformat()),
        )
    }
    note_row = db.execute(
        "SELECT note FROM week_notes WHERE child_id = ? AND week_start = ?",
        (child["id"], mon.isoformat()),
    ).fetchone()

    return render_template(
        "week.html",
        child=child,
        children=children,
        task_rows=task_rows,
        days=days,
        today_d=today_d,
        weekday_names=WEEKDAY_NAMES,
        day_totals=day_totals,
        day_counts=day_counts,
        week_score=round(week_score, 2),
        week_days=sum(1 for c in day_counts if c),
        settlement=settlement(db, child["id"], mon, sun),
        balance=balance_of(child["id"]),
        week_no=d.isocalendar()[1],
        week_start=mon,
        week_end=sun,
        prev_date=(mon - timedelta(days=1)).isoformat(),
        next_date=(mon + timedelta(days=7)).isoformat(),
        catalog=catalog,
        redeemed=redeemed,
        note=note_row["note"] if note_row else "",
    )


@bp.post("/week/note")
def week_note():
    child, early, _ = _need_child()
    if early:
        return early
    d = parse_iso(request.form.get("week_start"))
    if d:
        mon, _ = week_bounds(d)
        text = (request.form.get("note") or "").strip()
        db = get_db()
        if text:
            db.execute(
                """INSERT INTO week_notes(child_id, week_start, note) VALUES(?, ?, ?)
                   ON CONFLICT(child_id, week_start) DO UPDATE SET note = excluded.note""",
                (child["id"], mon.isoformat(), text),
            )
        else:
            db.execute(
                "DELETE FROM week_notes WHERE child_id = ? AND week_start = ?",
                (child["id"], mon.isoformat()),
            )
        db.commit()
        flash("已保存", "ok")
        return redirect(
            url_for("views.week", date=mon.isoformat(), child=child["id"])
        )
    return redirect(url_for("views.week"))


@bp.get("/passbook")
def passbook():
    child, early, children = _need_child()
    if early:
        return early
    now = local_today()
    y = request.args.get("year", type=int) or now.year
    m = request.args.get("month", type=int) or now.month
    try:
        first = date(y, m, 1)
    except ValueError:
        first = date(now.year, now.month, 1)
        y, m = first.year, first.month
    last = date(y, m, calendar.monthrange(y, m)[1])

    db = get_db()
    before = db.execute(
        """SELECT COALESCE(SUM(income), 0) AS inc, COALESCE(SUM(expense), 0) AS exp
           FROM ledger WHERE child_id = ? AND date < ?""",
        (child["id"], first.isoformat()),
    ).fetchone()
    running = child["initial_balance"] + before["inc"] - before["exp"]

    entries, tot_inc, tot_exp = [], 0.0, 0.0
    for r in db.execute(
        """SELECT * FROM ledger
           WHERE child_id = ? AND date BETWEEN ? AND ?
           ORDER BY date, id""",
        (child["id"], first.isoformat(), last.isoformat()),
    ):
        running += r["income"] - r["expense"]
        tot_inc += r["income"]
        tot_exp += r["expense"]
        item = dict(r)
        item["balance"] = round(running, 2)
        entries.append(item)

    pm, py = (12, y - 1) if m == 1 else (m - 1, y)
    nm, ny = (1, y + 1) if m == 12 else (m + 1, y)
    return render_template(
        "passbook.html",
        child=child,
        children=children,
        entries=entries,
        year=y,
        month=m,
        prev_query={"year": py, "month": pm},
        next_query={"year": ny, "month": nm},
        total_income=round(tot_inc, 2),
        total_expense=round(tot_exp, 2),
        balance=balance_of(child["id"]),
        initial_balance=child["initial_balance"],
        today_d=now,
        source_labels={"daily": "自动", "redeem": "兑换", "manual": "手动"},
    )


@bp.post("/passbook/add")
@admin_required
def passbook_add():
    child, early, _ = _need_child()
    if early:
        return early
    reason = (request.form.get("reason") or "").strip()
    d = parse_iso(request.form.get("date")) or local_today()
    try:
        income = float(request.form.get("income") or 0)
        expense = float(request.form.get("expense") or 0)
    except ValueError:
        income = expense = 0
    note = (request.form.get("note") or "").strip()
    if not reason or (income <= 0 and expense <= 0) or income < 0 or expense < 0:
        flash("请填写事由，并在收入或支出中填写正数", "error")
    elif income > 0 and expense > 0:
        flash("收入和支出只能填一项", "error")
    else:
        db = get_db()
        db.execute(
            """INSERT INTO ledger(child_id, date, reason, income, expense, note, source, created_by)
               VALUES(?, ?, ?, ?, ?, ?, 'manual', ?)""",
            (child["id"], d.isoformat(), reason, income, expense, note, session["user_id"]),
        )
        db.commit()
        flash("已记入存折", "ok")
    return redirect(
        url_for(
            "views.passbook",
            child=child["id"],
            year=d.year,
            month=d.month,
        )
    )


@bp.post("/passbook/delete")
@admin_required
def passbook_delete():
    db = get_db()
    row = db.execute(
        "SELECT * FROM ledger WHERE id = ?", (request.form.get("id", type=int) or -1,)
    ).fetchone()
    if not row:
        flash("记录不存在", "error")
    elif row["source"] == "daily":
        flash("每日得分由打卡自动生成，请到打卡页面取消勾选", "error")
    else:
        db.execute("DELETE FROM ledger WHERE id = ?", (row["id"],))
        db.commit()
        flash("已删除", "ok")
    return redirect(
        url_for(
            "views.passbook",
            child=row["child_id"] if row else None,
            year=(parse_iso(row["date"]).year if row else local_today().year),
            month=(parse_iso(row["date"]).month if row else local_today().month),
        )
    )


@bp.get("/redeem")
def redeem():
    child, early, children = _need_child()
    if early:
        return early
    db = get_db()
    items = db.execute(
        "SELECT * FROM catalog WHERE active = 1 ORDER BY sort_order, id"
    ).fetchall()
    now = local_today()
    first = date(now.year, now.month, 1)
    history = db.execute(
        """SELECT * FROM ledger
           WHERE child_id = ? AND source = 'redeem' AND date >= ?
           ORDER BY date DESC, id DESC LIMIT 50""",
        (child["id"], first.isoformat()),
    ).fetchall()
    balance = balance_of(child["id"])
    return render_template(
        "redeem.html",
        child=child,
        children=children,
        items=items,
        history=history,
        balance=balance,
        month_redemptions=round(sum(h["expense"] for h in history), 2),
    )


@bp.post("/redeem")
@admin_required
def redeem_do():
    child, early, _ = _need_child()
    if early:
        return early
    db = get_db()
    item = db.execute(
        "SELECT * FROM catalog WHERE id = ? AND active = 1",
        (request.form.get("item_id", type=int) or -1,),
    ).fetchone()
    if not item:
        flash("商品不存在", "error")
    elif balance_of(child["id"]) < item["price"]:
        flash("余额不足，先攒攒分吧", "error")
    else:
        db.execute(
            """INSERT INTO ledger(child_id, date, reason, expense, source, created_by)
               VALUES(?, ?, ?, ?, 'redeem', ?)""",
            (child["id"], local_today().isoformat(), item["name"], item["price"], session["user_id"]),
        )
        db.commit()
        flash(f"已兑换「{item['name']}」，支出 {item['price']:g} 分", "ok")
    return redirect(url_for("views.redeem", child=child["id"]))


@bp.post("/catalog/add")
@admin_required
def catalog_add():
    name = (request.form.get("name") or "").strip()
    try:
        price = float(request.form.get("price") or 0)
    except ValueError:
        price = 0
    if not name or price <= 0:
        flash("请填写商品名称和正数价格", "error")
    else:
        db = get_db()
        db.execute(
            "INSERT INTO catalog(name, price, sort_order) VALUES(?, ?, "
            "(SELECT COALESCE(MAX(sort_order), 0) + 1 FROM catalog))",
            (name, price),
        )
        db.commit()
        flash("已添加", "ok")
    return redirect(url_for("views.redeem"))


@bp.post("/catalog/update")
@admin_required
def catalog_update():
    item_id = request.form.get("id", type=int)
    name = (request.form.get("name") or "").strip()
    try:
        price = float(request.form.get("price") or 0)
    except ValueError:
        price = 0
    db = get_db()
    if not item_id or not name or price <= 0:
        flash("名称和价格必须有效", "error")
    else:
        db.execute(
            "UPDATE catalog SET name = ?, price = ? WHERE id = ?",
            (name, price, item_id),
        )
        db.commit()
        flash("已更新", "ok")
    return redirect(url_for("views.redeem"))


@bp.post("/catalog/delete")
@admin_required
def catalog_delete():
    db = get_db()
    db.execute("DELETE FROM catalog WHERE id = ?", (request.form.get("id", type=int) or -1,))
    db.commit()
    flash("已删除", "ok")
    return redirect(url_for("views.redeem"))


def _month_data(db, child, y: int, m: int) -> dict:
    first = date(y, m, 1)
    last = date(y, m, calendar.monthrange(y, m)[1])
    iso_first, iso_last = first.isoformat(), last.isoformat()
    n_days = last.day
    labels = [str(i) for i in range(1, n_days + 1)]
    dates = [date(y, m, i).isoformat() for i in range(1, n_days + 1)]

    led = {
        r["date"]: (r["inc"], r["exp"])
        for r in db.execute(
            """SELECT date, SUM(income) AS inc, SUM(expense) AS exp FROM ledger
               WHERE child_id = ? AND date BETWEEN ? AND ? GROUP BY date""",
            (child["id"], iso_first, iso_last),
        )
    }
    daily = {
        r["date"]: r["s"]
        for r in db.execute(
            """SELECT date, SUM(income) AS s FROM ledger
               WHERE child_id = ? AND source = 'daily' AND date BETWEEN ? AND ?
               GROUP BY date""",
            (child["id"], iso_first, iso_last),
        )
    }
    checkins = {
        r["date"]: r["c"]
        for r in db.execute(
            """SELECT date, COUNT(*) AS c FROM checkins
               WHERE child_id = ? AND date BETWEEN ? AND ? GROUP BY date""",
            (child["id"], iso_first, iso_last),
        )
    }

    before = db.execute(
        """SELECT COALESCE(SUM(income), 0) AS i, COALESCE(SUM(expense), 0) AS e
           FROM ledger WHERE child_id = ? AND date < ?""",
        (child["id"], iso_first),
    ).fetchone()
    bal = child["initial_balance"] + before["i"] - before["e"]
    balances = []
    for ds in dates:
        inc, exp = led.get(ds, (0.0, 0.0))
        bal += inc - exp
        balances.append(round(bal, 2))

    expenses = [
        {"label": r["reason"], "value": round(r["s"], 2)}
        for r in db.execute(
            """SELECT reason, SUM(expense) AS s FROM ledger
               WHERE child_id = ? AND expense > 0 AND date BETWEEN ? AND ?
               GROUP BY reason ORDER BY s DESC""",
            (child["id"], iso_first, iso_last),
        )
    ]
    task_counts = [
        {"label": r["name"], "value": r["c"]}
        for r in db.execute(
            """SELECT t.name AS name, COUNT(*) AS c FROM checkins ck
               JOIN tasks t ON t.id = ck.task_id
               WHERE ck.child_id = ? AND ck.date BETWEEN ? AND ?
               GROUP BY t.id ORDER BY c DESC""",
            (child["id"], iso_first, iso_last),
        )
    ]

    month_income = round(sum(v[0] for v in led.values()), 2)
    month_expense = round(sum(v[1] for v in led.values()), 2)
    days_tracked = len(checkins)
    total_checkins = sum(checkins.values())
    month_score = round(sum(daily.values()), 2)

    return {
        "year": y,
        "month": m,
        "labels": labels,
        "daily_scores": [round(daily.get(ds, 0), 2) for ds in dates],
        "balances": balances,
        "expenses": expenses,
        "task_counts": task_counts,
        "stats": {
            "month_score": month_score,
            "month_income": month_income,
            "month_expense": month_expense,
            "closing_balance": balances[-1] if balances else 0,
            "days_tracked": days_tracked,
            "total_checkins": total_checkins,
        },
    }


@bp.get("/charts")
def charts():
    child, early, children = _need_child()
    if early:
        return early
    now = local_today()
    y = request.args.get("year", type=int) or now.year
    m = request.args.get("month", type=int) or now.month
    try:
        date(y, m, 1)
    except ValueError:
        y, m = now.year, now.month
    data = _month_data(get_db(), child, y, m)
    pm, py = (12, y - 1) if m == 1 else (m - 1, y)
    nm, ny = (1, y + 1) if m == 12 else (m + 1, y)
    return render_template(
        "charts.html",
        child=child,
        children=children,
        year=y,
        month=m,
        prev_query={"year": py, "month": pm},
        next_query={"year": ny, "month": nm},
        chart_data=data,
        balance=balance_of(child["id"]),
    )


@bp.get("/help")
def help():
    child, children = current_child()
    return render_template("help.html", child=child, children=children)
