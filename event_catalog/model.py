"""Shared event, provenance and theory contracts. All times in manifests use UTC."""

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
KINDS = {
    "detection",
    "measurement",
    "upper_limit",
    "non_detection",
    "no_coverage",
    "product",
    "notice",
    "publication",
}


def dump(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def label(value):
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def utc(value):
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.utcoffset() is None:
        raise ValueError("UTC timestamp must include its timezone")
    return date.astimezone(timezone.utc)


def bounds(value):
    if (
        len(value) != 2
        or not all(math.isfinite(x) for x in value)
        or value[0] > value[1]
    ):
        raise ValueError(f"invalid interval {value}")
    return value


def validate_event(event):
    if event.get("schema") != 1 or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.+-]*", event["id"]
    ):
        raise ValueError("use schema 1 and a stable event ID")
    if event["status"] not in {"provisional", "confirmed", "retracted"}:
        raise ValueError("unknown event status")
    if event["origin"] not in {"observed", "synthetic"}:
        raise ValueError("declare observed or synthetic origin")
    if event.get("utc"):
        utc(event["utc"])
    bounds(event["search_days"])
    for ra, dec, radius in event["regions_deg"]:
        if not (0 <= ra < 360 and -90 <= dec <= 90 and 0 < radius <= 180):
            raise ValueError("invalid ICRS search cone")
    if not isinstance(event.get("aliases"), list) or any(
        not label(x) for x in event["aliases"]
    ):
        raise ValueError("aliases must be a list of nonempty event/counterpart names")
    return event


def check_record(r):
    for k in (
        "key",
        "sensor",
        "channel",
        "subject",
        "reference",
        "description",
        "resource",
    ):
        if not isinstance(r.get(k), str) or not r[k].strip():
            raise ValueError(f"missing {k} in {r.get('key')}")
    if not r["reference"].startswith(("https://", "http://", "ivo://", "doi:")):
        raise ValueError("record needs a traceable reference")
    if r.get("kind") not in KINDS or r.get("association") not in {
        "confirmed",
        "candidate",
        "rejected",
    }:
        raise ValueError("invalid evidence kind or association")
    if not isinstance(r.get("lineage"), list) or any(
        not isinstance(x, str) or not x for x in r["lineage"]
    ):
        raise ValueError("lineage must list underlying data families")
    for key in ("time_s", "band_MeV"):
        if key in r:
            bounds(r[key])
    if "value" in r and (not math.isfinite(r["value"]) or not r.get("unit")):
        raise ValueError("quantitative evidence needs a finite value and a unit")
    if "sigma" in r and (
        not math.isfinite(r["sigma"]) or r["sigma"] < 0 or "value" not in r
    ):
        raise ValueError("invalid measurement uncertainty")
    if "confidence" in r and not 0 < r["confidence"] < 1:
        raise ValueError("invalid confidence level")
    if r.get("level", "summary") not in {"summary", "locator", "checked_file"}:
        raise ValueError("unknown evidence level")
    if r.get("level") == "checked_file" and not re.fullmatch(
        r"[0-9a-f]{64}", r.get("sha256", "")
    ):
        raise ValueError("checked_file requires a verified SHA-256")
    return r


def record(key, sensor, channel, subject, kind, resource, ref, description, **fields):
    return dict(
        key=key,
        sensor=sensor,
        channel=channel,
        subject=subject,
        kind=kind,
        resource=resource,
        reference=ref,
        description=description,
        association="candidate",
        lineage=[],
        **fields,
    )


def requirements(rows, theory, event):
    """Test declared input compatibility, including shared detector constraints."""
    names = set()
    results = []
    for req in theory["requires"]:
        if req["id"] in names or not req.get("match"):
            raise ValueError(
                "requirement names must be distinct and match criteria nonempty"
            )
        names.add(req["id"])
        for key in req.get("covers", {}):
            if key not in ("time_s", "band_MeV"):
                raise ValueError("unsupported interval")
            bounds(req["covers"][key])
        candidates, usable = [], []
        for row in rows:
            if any(row.get(k) != v for k, v in req["match"].items()):
                continue
            candidates.append(row["id"])
            if (
                row["stale"]
                or row["association"] != "confirmed"
                or row["kind"] in {"no_coverage", "notice", "publication"}
            ):
                continue
            if row.get("level", "summary") != req["level"]:
                continue
            if any(
                k not in row or row[k][0] > a or row[k][1] < b
                for k, (a, b) in req.get("covers", {}).items()
            ):
                continue
            usable.append(row)
        results.append(
            {
                "id": req["id"],
                "sensor_group": req.get("same_sensor"),
                "candidates": candidates,
                "usable": usable,
            }
        )
    for group in {r["sensor_group"] for r in results if r["sensor_group"]}:
        members = [r for r in results if r["sensor_group"] == group]
        common = set.intersection(
            *({row["sensor"] for row in r["usable"]} for r in members)
        )
        for r in members:
            r["common_sensors"] = sorted(common)
    complete = bool(results) and all(
        r["usable"] and ("common_sensors" not in r or r["common_sensors"])
        for r in results
    )
    for r in results:
        r["usable"] = [x["id"] for x in r["usable"]]
    return {
        "theory": theory["name"],
        "inputs_complete": bool(complete and event["status"] != "retracted"),
        "event_status": event["status"],
        "origin": event["origin"],
        "requirements": results,
    }


def corroboration(rows):
    """List distinct observational lineages reporting the same stated phenomenon."""
    groups = {}
    for r in rows:
        if (
            r["kind"] != "detection"
            or r["association"] != "confirmed"
            or r["stale"]
            or not r["lineage"]
        ):
            continue
        groups.setdefault(r["subject"], []).append(r)
    result = []
    for name, group in groups.items():
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                if a["sensor"] != b["sensor"] and set(a["lineage"]).isdisjoint(
                    b["lineage"]
                ):
                    result.append(
                        {
                            "subject": name,
                            "evidence": [a["id"], b["id"]],
                            "sensors": [a["sensor"], b["sensor"]],
                        }
                    )
    return result


def comparisons(rows):
    """For curator-declared comparable Gaussian estimates, report the difference in sigma."""
    groups = {}
    for r in rows:
        if (
            r.get("comparison_key")
            and r.get("uncertainty") == "gaussian_1sigma"
            and "sigma" in r
            and r["association"] == "confirmed"
            and not r["stale"]
            and r["lineage"]
            and r["kind"] in {"detection", "measurement"}
        ):
            key = (r["comparison_key"], r["subject"], r["resource"], r["unit"])
            groups.setdefault(key, []).append(r)
    result = []
    for (key, *_), group in groups.items():
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                uncertainty = math.hypot(a["sigma"], b["sigma"])
                if (
                    uncertainty
                    and a["sensor"] != b["sensor"]
                    and set(a["lineage"]).isdisjoint(b["lineage"])
                ):
                    result.append(
                        {
                            "comparison_key": key,
                            "evidence": [a["id"], b["id"]],
                            "difference_sigma": (a["value"] - b["value"]) / uncertainty,
                        }
                    )
    return result
