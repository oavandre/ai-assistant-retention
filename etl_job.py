import argparse
import sqlite3
import time
from contextlib import closing
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from etl import DATA, DB, REPO, build

ZONE = ZoneInfo("America/Sao_Paulo")
DAYS = ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo")
MESSAGES = {
    "running": "Em execução",
    "updated": "Base atualizada",
    "unchanged": "Fonte sem nova revisão",
    "failed": "Falha na execução",
}


def connect():
    DATA.mkdir(exist_ok=True)
    db = sqlite3.connect(DATA / "etl_job.sqlite")
    db.row_factory = sqlite3.Row
    db.execute("""
        CREATE TABLE IF NOT EXISTS job (
            id INTEGER PRIMARY KEY CHECK (id = 1), enabled INTEGER DEFAULT 0,
            frequency TEXT DEFAULT 'daily', hour TEXT DEFAULT '06:00',
            weekday INTEGER DEFAULT 0, saved_at TEXT, slot TEXT,
            started TEXT, finished TEXT, status TEXT, heartbeat TEXT
        )
    """)
    with db:
        db.execute("INSERT OR IGNORE INTO job(id) VALUES (1)")
    return db


def settings():
    with closing(connect()) as db:
        return dict(db.execute("SELECT * FROM job WHERE id = 1").fetchone())


def save(enabled, frequency, hour, weekday):
    if frequency not in ("daily", "weekly") or weekday not in range(7):
        raise ValueError("Agendamento inválido.")
    datetime.strptime(hour, "%H:%M")
    with closing(connect()) as db, db:
        db.execute("""
            UPDATE job SET enabled=?, frequency=?, hour=?, weekday=?, saved_at=? WHERE id=1
        """, (enabled, frequency, hour, weekday, datetime.now(ZONE).isoformat()))


def due_slot(config, now):
    if not config["enabled"]:
        return None
    if config["frequency"] == "weekly" and now.weekday() != config["weekday"]:
        return None
    hour, minute = map(int, config["hour"].split(":"))
    slot = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    saved = config["saved_at"]
    if slot > now or (saved and slot < datetime.fromisoformat(saved)):
        return None
    key = slot.isoformat()
    return key if key != config["slot"] else None


def refresh():
    response = requests.get(f"https://huggingface.co/api/datasets/{REPO}/revision/main", timeout=25)
    response.raise_for_status()
    revision = response.json()["sha"]
    if DB.is_file():
        with closing(sqlite3.connect(DB.as_uri() + "?mode=ro", uri=True)) as db:
            current = db.execute("SELECT valor FROM auditoria WHERE item=?",
                                 ("revisão WildChat-1M",)).fetchone()
        if current and current[0] == revision:
            return "unchanged"
    build(revision=revision)
    return "updated"


def tick():
    now = datetime.now(ZONE)
    with closing(connect()) as db, db:
        db.execute("UPDATE job SET heartbeat=? WHERE id=1", (now.isoformat(),))
    # A transação neste arquivo separado impede duas cargas simultâneas pelo agendador.
    with closing(sqlite3.connect(DATA / "etl_job_lock.sqlite", timeout=0)) as lock:
        try:
            lock.execute("BEGIN EXCLUSIVE")
        except sqlite3.OperationalError as exc:
            if exc.sqlite_errorcode == sqlite3.SQLITE_BUSY:
                return
            raise
        config = settings()
        if config["status"] == "running":
            with closing(connect()) as db, db:
                db.execute("UPDATE job SET finished=?, status='failed' WHERE id=1", (now.isoformat(),))
        slot = due_slot(config, now)
        if not slot:
            return
        with closing(connect()) as db, db:
            db.execute("UPDATE job SET slot=?, started=?, finished=NULL, status='running' WHERE id=1",
                       (slot, now.isoformat()))
        status = "failed"
        try:
            status = refresh()
        finally:
            with closing(connect()) as db, db:
                db.execute("UPDATE job SET finished=?, status=? WHERE id=1",
                           (datetime.now(ZONE).isoformat(), status))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="Verifica o agendamento a cada minuto.")
    args = parser.parse_args()
    while True:
        try:
            tick()
        except Exception as exc:
            print(f"ETL: {type(exc).__name__}: {exc}", flush=True)
            if not args.loop:
                raise
        if not args.loop:
            break
        time.sleep(60)
