"""Append-only source attempts and content-addressed sets of evidence."""

import json
import sqlite3
from datetime import datetime, timezone

from .archives import ADAPTERS, DEFAULTS, Reader, Skip
from .model import (
    check_record,
    comparisons,
    corroboration,
    digest,
    dump,
    label,
    requirements,
    validate_event,
)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path):
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, manifest TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS batches(hash TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY, event TEXT REFERENCES events(id),
            source TEXT NOT NULL, scope TEXT NOT NULL, started TEXT NOT NULL, ended TEXT,
            status TEXT NOT NULL, batch TEXT REFERENCES batches(hash), note TEXT, receipts TEXT);
        CREATE INDEX IF NOT EXISTS event_attempts ON attempts(event,source,scope,id);
    """)
    return conn


def sources(event):
    out = dict(DEFAULTS)
    out.update(event.get("sources", {}))
    return {k: v for k, v in out.items() if v is not None}


def scope(event, name, cfg):
    # Updating reviewed evidence does not invalidate unrelated archive queries.
    basis = {k: v for k, v in event.items() if k not in ("sources", "evidence")}
    if cfg["adapter"] == "curated":
        basis["evidence"] = event.get("evidence", [])
    return digest(dump([basis, name, cfg]).encode())


def sync(conn, event, base, selected=None, reader_factory=Reader):
    validate_event(event)
    configs = sources(event)
    chosen = list(configs) if selected is None else list(dict.fromkeys(selected))
    if set(chosen) - configs.keys():
        raise ValueError("unknown or disabled source in --only")
    for name, cfg in configs.items():
        if cfg["adapter"] not in ADAPTERS:
            raise ValueError(f"unknown adapter for {name}")
        if "limit" in cfg and not (
            isinstance(cfg["limit"], int) and 1 <= cfg["limit"] <= 10000
        ):
            raise ValueError(f"invalid row limit for {name}")
        if "pages" in cfg and not (
            isinstance(cfg["pages"], int) and 1 <= cfg["pages"] <= 1000
        ):
            raise ValueError(f"invalid page limit for {name}")
    with conn:
        conn.execute(
            "INSERT INTO events VALUES(?,?) ON CONFLICT(id) DO UPDATE SET manifest=excluded.manifest",
            (event["id"], dump(event)),
        )
    log = []
    for name in chosen:
        cfg = configs[name]
        key = scope(event, name, cfg)
        with conn:
            run = conn.execute(
                "INSERT INTO attempts(event,source,scope,started,status) VALUES(?,?,?,?,?)",
                (event["id"], name, key, now(), "running"),
            ).lastrowid
        reader = reader_factory()
        batch, payload, note = None, None, ""
        try:
            records, partial = ADAPTERS[cfg["adapter"]](
                event, dict(cfg, base=str(base)), reader
            )
            items = {}
            for r in records:
                check_record(r)
                if r["key"] in items and r != items[r["key"]]:
                    raise ValueError(f"conflicting rows share source key {r['key']}")
                items[r["key"]] = r
            payload = dump([items[k] for k in sorted(items)])
            batch = digest(payload.encode())
            status = "partial" if partial else ("returned" if items else "empty")
            note = f"{len(items)} records"
        except Skip as error:
            status, note = "missing_input", str(error)
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            EOFError,
            ArithmeticError,
        ) as error:
            status, note = "failed", str(error)
        except Exception as error:
            # XML, tar and HTTP parser exceptions vary by provider. A failed adapter
            # must leave the previous snapshot available and other sources runnable.
            status, note = "failed", f"{type(error).__name__}: {error}"
        with conn:
            if batch:
                conn.execute(
                    "INSERT OR IGNORE INTO batches VALUES(?,?)", (batch, payload)
                )
            conn.execute(
                "UPDATE attempts SET ended=?,status=?,batch=?,note=?,receipts=? WHERE id=?",
                (now(), status, batch, note, dump(reader.receipts), run),
            )
        log.append({"source": name, "status": status, "note": note, "attempt": run})
    return log


def resolve(conn, query):
    found = []
    for (data,) in conn.execute("SELECT manifest FROM events"):
        event = json.loads(data)
        if label(query) in {label(x) for x in [event["id"], *event["aliases"]]}:
            found.append(event)
    if len(found) != 1:
        raise ValueError(
            f"{query!r} matched {len(found)} events; use a unique event ID"
        )
    return found[0]


def dossier(conn, query, theory=None):
    event = resolve(conn, query)
    coverage, rows = {}, []
    for name, cfg in sources(event).items():
        args = (event["id"], name, scope(event, name, cfg))
        sql = "SELECT * FROM attempts WHERE event=? AND source=? AND scope=? "
        last = conn.execute(sql + "ORDER BY id DESC LIMIT 1", args).fetchone()
        good = conn.execute(
            sql + "AND batch IS NOT NULL ORDER BY id DESC LIMIT 1", args
        ).fetchone()
        coverage[name] = (
            {"status": "unqueried"}
            if not last
            else {k: last[k] for k in ("id", "ended", "status", "note")}
        )
        if good:
            batch = conn.execute(
                "SELECT data FROM batches WHERE hash=?", (good["batch"],)
            ).fetchone()
            coverage[name].update(
                batch_sha256=good["batch"],
                snapshot_attempt=good["id"],
                receipts=json.loads(good["receipts"]),
            )
            for r in json.loads(batch["data"]):
                rows.append(
                    dict(
                        r,
                        id=f"{name}/{r['key']}",
                        stale=good["id"] != last["id"],
                        source=name,
                    )
                )
    out = {
        "event": {k: v for k, v in event.items() if k != "evidence"},
        "coverage": coverage,
        "evidence": rows,
        "corroboration": corroboration(rows),
        "quantitative_comparisons": comparisons(rows),
    }
    if theory:
        out["theory"] = requirements(rows, theory, event)
    return out
