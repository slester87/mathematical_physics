"""Run with python3 -m event_catalog --help."""

import argparse
import json
import sys
from pathlib import Path
from .archives import Reader, registry
from .model import validate_event
from .store import connect, dossier, resolve, sync


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def template(a):
    event = {
        "schema": 1,
        "id": a.id,
        "aliases": a.alias,
        "status": "provisional",
        "origin": "observed",
        "utc": a.utc,
        "regions_deg": a.cone,
        "search_days": a.days,
        "identifiers": {
            k: v
            for k, v in (("gwosc", a.gwosc), ("gracedb", a.gracedb), ("gbm", a.gbm))
            if v
        },
        "sources": {},
        "evidence": [],
    }
    validate_event(event)
    return event


def markdown(d):
    e = d["event"]
    lines = [
        f"# {e['id']}",
        "",
        f"{e['origin']} · {e['status']} · " + (e.get("utc") or "epoch unknown"),
        "",
        "## Archive coverage",
        "",
        "| Source | Latest search |",
        "|---|---|",
    ]
    for src, v in d["coverage"].items():
        lines.append(f"| {src} | {v['status']} {v.get('note', '')} |")
    lines += [
        "",
        "## Evidence",
        "",
        "| Sensor | Evidence | Association | Source |",
        "|---|---|---|---|",
    ]
    for r in d["evidence"]:
        name = r["description"].replace("|", "/").replace("\n", " ")
        if "value" in r:
            sign = "< " if r["kind"] == "upper_limit" else ""
            uncertainty = f" ± {r['sigma']:g}" if "sigma" in r else ""
            name += f" ({sign}{r['value']:g}{uncertainty} {r['unit']})"
        lines.append(
            f"| {r['sensor']} | {r['kind']}: {name} | {r['association']}"
            + (" (stale)" if r["stale"] else "")
            + f" | [source]({r['reference']}) |"
        )
    lines += ["", "## Corroboration", ""]
    for pair in d["corroboration"]:
        lines.append(f"- {pair['subject']} — " + " and ".join(pair["sensors"]))
    if not d["corroboration"]:
        lines.append("No pair with distinct recorded data lineages.")
    if d["quantitative_comparisons"]:
        lines += ["", "## Comparable measurements", ""]
        for pair in d["quantitative_comparisons"]:
            lines.append(
                f"- {pair['comparison_key']} — difference {pair['difference_sigma']:.3g} σ; "
                + " / ".join(pair["evidence"])
            )
    if "theory" in d:
        t = d["theory"]
        lines += [
            "",
            "## Theory inputs",
            "",
            t["theory"],
            "",
            f"Inputs complete: {t['inputs_complete']}",
            "",
        ]
        for req in t["requirements"]:
            lines.append(
                f"- {req['id']} — {len(req['usable'])} usable, {len(req['candidates'])} matched"
            )
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(
        description="Build and query per-event astronomical evidence dossiers"
    )
    p.add_argument("--db", type=Path, default=Path(".event-catalog.sqlite"))
    cmds = p.add_subparsers(dest="cmd", required=True)
    new = cmds.add_parser("new", help="print a manifest for an event of any class")
    new.add_argument("id")
    new.add_argument("--alias", action="append", default=[])
    new.add_argument("--utc")
    new.add_argument(
        "--cone",
        nargs=3,
        type=float,
        action="append",
        default=[],
        metavar=("RA", "DEC", "RADIUS"),
    )
    new.add_argument("--days", nargs=2, type=float, default=[-1, 30])
    for opt in ("gwosc", "gracedb", "gbm"):
        new.add_argument("--" + opt)
    s = cmds.add_parser(
        "sync", help="import reviewed evidence and discover archive records"
    )
    s.add_argument("manifest", type=Path)
    s.add_argument("--only", nargs="+")
    s.add_argument("--archives", type=Path, help="additional archive registry JSON")
    r = cmds.add_parser("report")
    r.add_argument("event")
    r.add_argument("--theory", type=Path)
    r.add_argument("--format", choices=("markdown", "json"), default="markdown")
    h = cmds.add_parser("history")
    h.add_argument("event")
    get = cmds.add_parser(
        "snapshot", help="retrieve an immutable evidence batch by SHA-256"
    )
    get.add_argument("sha256")
    cmds.add_parser(
        "discover-archives",
        help="print interoperable archive endpoints from the IVOA registry",
    )
    a = p.parse_args()
    try:
        if a.cmd == "new":
            data = template(a)
        elif a.cmd == "discover-archives":
            data = registry(Reader())
        else:
            with connect(a.db) as db:
                if a.cmd == "sync":
                    event = read(a.manifest)
                    if a.archives:
                        event["sources"] = {
                            **read(a.archives)["sources"],
                            **event.get("sources", {}),
                        }
                    data = sync(db, event, a.manifest.resolve().parent, a.only)
                    print(json.dumps(data, indent=2))
                    return int(any(r["status"] == "failed" for r in data))
                if a.cmd == "report":
                    data = dossier(db, a.event, read(a.theory) if a.theory else None)
                    if a.format == "markdown":
                        print(markdown(data))
                        return 0
                elif a.cmd == "history":
                    event = resolve(db, a.event)
                    data = [
                        dict(r)
                        for r in db.execute(
                            "SELECT id,source,started,ended,status,note,batch FROM attempts WHERE event=? ORDER BY id",
                            (event["id"],),
                        )
                    ]
                elif a.cmd == "snapshot":
                    row = db.execute(
                        "SELECT data FROM batches WHERE hash=?", (a.sha256,)
                    ).fetchone()
                    if row is None:
                        raise ValueError("unknown snapshot")
                    data = json.loads(row[0])
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, KeyError, OSError) as err:
        p.exit(2, f"{p.prog}: {err}\n")


if __name__ == "__main__":
    sys.exit(main())
