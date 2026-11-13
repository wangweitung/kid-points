import os
import sqlite3
from pathlib import Path

from flask import g

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    session_ver INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS children (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    initial_balance REAL NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    value REAL NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS checkins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (child_id, task_id, date)
);

CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    reason TEXT NOT NULL,
    income REAL NOT NULL DEFAULT 0,
    expense REAL NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'manual',
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ledger_daily
    ON ledger(child_id, date) WHERE source = 'daily';
CREATE INDEX IF NOT EXISTS ix_ledger_child_date ON ledger(child_id, date);
CREATE INDEX IF NOT EXISTS ix_checkins_child_date ON checkins(child_id, date);

CREATE TABLE IF NOT EXISTS catalog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    price REAL NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS week_notes (
    child_id INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    week_start TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (child_id, week_start)
);
"""

SEED_TASKS = [
    ("专注打卡 15分钟，不离座不打岔", 10),
    ("每日中文阅读 15 分钟", 5),
    ("每日英文阅读 10 分钟", 5),
    ("每日主动跳绳100个以上", 5),
    ("上学日自己整理书包", 2),
    ("每日早起没有起床气", 2),
    ("帮了身边人，或做一件家务", 2),
]

SEED_CATALOG = [
    ("购买一个奇趣蛋", 100),
    ("套50元圈一次", 1000),
    ("购买一个珍珠礼盒", 500),
    ("套100元圈一次", 10000),
]


def init_app(app):
    app.teardown_appcontext(close_db)


def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR") or DEFAULT_DATA_DIR)


def db_path() -> Path:
    return data_dir() / "points.db"


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        path = db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        g.db = conn
    return g.db


def ensure_schema():
    db = get_db()
    db.executescript(SCHEMA)
    cols = {r["name"] for r in db.execute("PRAGMA table_info(users)")}
    if "session_ver" not in cols:
        db.execute(
            "ALTER TABLE users ADD COLUMN session_ver INTEGER NOT NULL DEFAULT 0"
        )
    if db.execute("SELECT COUNT(*) AS c FROM tasks").fetchone()["c"] == 0:
        for i, (name, value) in enumerate(SEED_TASKS):
            db.execute(
                "INSERT INTO tasks(name, value, sort_order) VALUES(?, ?, ?)",
                (name, value, i),
            )
    if db.execute("SELECT COUNT(*) AS c FROM catalog").fetchone()["c"] == 0:
        for i, (name, price) in enumerate(SEED_CATALOG):
            db.execute(
                "INSERT INTO catalog(name, price, sort_order) VALUES(?, ?, ?)",
                (name, price, i),
            )
    if db.execute("SELECT COUNT(*) AS c FROM children").fetchone()["c"] == 0:
        db.execute("INSERT INTO children(name, initial_balance) VALUES('Morning', 0)")
    if db.execute("SELECT COUNT(*) AS c FROM settings").fetchone()["c"] == 0:
        db.execute("INSERT INTO settings(key, value) VALUES('registration_open', '0')")
    db.commit()


def has_users() -> bool:
    return get_db().execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None


def get_setting(key: str, default: str = "") -> str:
    row = get_db().execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    db = get_db()
    db.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    db.commit()
