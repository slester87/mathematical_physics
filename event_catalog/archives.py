"""Archive-specific discovery. Search matches remain candidates until reviewed."""

import csv
import hashlib
import io
import json
import re
import tarfile
import time
from urllib.error import HTTPError
import urllib.parse as url
import urllib.request as http
import xml.etree.ElementTree as ET
from pathlib import Path

from .model import check_record, digest, record, utc

DEFAULTS = {
    "reviewed": {"adapter": "curated"},
    "gwosc": {"adapter": "gwosc"},
    "gracedb": {"adapter": "gracedb"},
    "fermi": {"adapter": "fermi"},
    "gcn": {"adapter": "gcn"},
    "mast": {
        "adapter": "mast",
        "url": "https://mast.stsci.edu/api/v0/invoke",
    },
    "eso": {"adapter": "obscore", "url": "https://archive.eso.org/tap_obs/sync"},
    "literature": {"adapter": "crossref"},
    "arxiv": {"adapter": "arxiv"},
}
GCN_ARCHIVE = "https://gcn.nasa.gov/circulars/archive.json.tar.gz"


class Skip(Exception):
    """Required identifier, time, or region is unavailable."""


class Reader:
    def __init__(self):
        self.receipts = []

    def get(self, uri, form=None):
        body = url.urlencode(form).encode() if form else None
        req = http.Request(
            uri,
            data=body,
            headers={
                "User-Agent": "MathematicalPhysicsEventCatalog/1.0 (https://github.com/slester87/mathematical_physics)"
            },
        )
        entry = {"url": uri}
        if form:
            entry["form"] = form
        self.receipts.append(entry)
        for attempt in range(3):
            try:
                with http.urlopen(req, timeout=45) as resp:
                    data = resp.read(100_000_001)
                break
            except HTTPError as exc:
                if attempt == 2 or exc.code not in (429, 502, 503, 504):
                    raise
                delay = exc.headers.get("Retry-After", "")
                if delay.isdigit() and int(delay) > 30:
                    raise
                time.sleep(int(delay) if delay.isdigit() else 2 ** (attempt + 1))
        if len(data) > 100_000_000:
            raise ValueError("metadata response exceeds 100 MB")
        entry["response_sha256"] = digest(data)
        return data

    def json(self, uri):
        return json.loads(self.get(uri))


def curated(event, cfg, get):
    rows = []
    # File paths are resolved relative to the event manifest during import.
    for item in event.get("evidence", []):
        r = dict(item)
        if r.get("level") == "checked_file":
            path = Path(cfg["base"]) / r["file"]
            with path.open("rb") as f:
                checksum = hashlib.file_digest(f, "sha256").hexdigest()
            if checksum != r["sha256"]:
                raise ValueError(f"checksum mismatch for {r['key']}")
        rows.append(check_record(r))
    return rows, False


def measurement_csv(event, cfg, get):
    """Map a publisher's CSV to typed evidence while retaining original columns."""
    if "path" in cfg:
        data = (Path(cfg["base"]) / cfg["path"]).read_bytes()
        get.receipts.append(
            {"local_table": cfg["path"], "response_sha256": digest(data)}
        )
    else:
        data = get.get(cfg["url"])
    if "sha256" in cfg and digest(data) != cfg["sha256"]:
        raise ValueError("measurement table checksum mismatch")
    table = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    required = set(cfg["columns"].values()) | set(cfg.get("select", {}))
    if not required.issubset(table.fieldnames or []):
        raise ValueError("table is missing declared columns")
    if not cfg.get("single_event") and not cfg.get("select"):
        raise ValueError("declare a single-event table or specify a row selection")
    rows = []
    for original in table:
        if any(original[k] != v for k, v in cfg.get("select", {}).items()):
            continue
        r = dict(cfg["defaults"])
        for field, col in cfg["columns"].items():
            raw = original[col]
            if raw != "":
                r[field] = (
                    float(raw) if field in ("value", "sigma", "confidence") else raw
                )
        r["metadata"] = {"original_row": original}
        r.setdefault("association", "candidate")
        r.setdefault("lineage", [])
        if r.get("level") == "checked_file":
            raise ValueError("use the reviewed adapter to attach a checked file")
        rows.append(r)
    return rows, False


def gwosc(event, cfg, get):
    version = event.get("identifiers", {}).get("gwosc")
    if not version:
        raise Skip("No GWOSC event-version identifier")
    uri = f"https://gwosc.org/api/v2/event-versions/{url.quote(version, safe='')}?format=json"
    info = get.json(uri)
    if version != f"{info['name']}-v{info['version']}":
        raise ValueError("GWOSC returned another event version")
    rows = []
    for prop in ("strain_files_url", "parameters_url", "timelines_url"):
        r = record(
            prop,
            "GWOSC",
            "GW",
            "gravitational-wave signal",
            "product",
            prop[:-4],
            uri,
            f"{info['catalog']} {version} {prop[:-4]}",
            uri=info[prop],
            level="locator",
        )
        r.update(
            association="confirmed",
            lineage=[version],
            metadata={
                "gps": info["gps"],
                "archive_detectors": info["detectors"],
                "doi": info.get("doi"),
            },
        )
        rows.append(r)
    return rows, False


def gracedb(event, cfg, get):
    sid = event.get("identifiers", {}).get("gracedb")
    if not sid:
        raise Skip("No public GraceDB superevent ID")
    uri = "https://gracedb.ligo.org/api/superevents/" + url.quote(sid, safe="") + "/"
    data = get.json(uri)
    if data["superevent_id"] != sid:
        raise ValueError("GraceDB identity mismatch")
    return [
        record(
            sid,
            "GraceDB",
            "GW",
            "alert",
            "notice",
            "alert",
            uri,
            f"Public superevent {sid}",
            metadata={
                k: data.get(k) for k in ("t_0", "preferred_event", "labels", "links")
            },
        )
    ], False


def fermi(event, cfg, get):
    trig = event.get("identifiers", {}).get("gbm")
    if not trig:
        raise Skip("No associated GBM trigger ID")
    if not re.fullmatch(r"bn\d{9}", trig):
        raise ValueError("expected GBM ID bnYYMMDDfff")
    base = "https://nasa-heasarc.s3.us-east-1.amazonaws.com/"
    prefix = f"fermi/data/gbm/triggers/20{trig[2:4]}/{trig}/current/"
    rows, token, seen = [], None, set()
    while True:
        params = {"list-type": "2", "prefix": prefix}
        if token:
            params["continuation-token"] = token
        doc = ET.fromstring(get.get(base + "?" + url.urlencode(params)))
        if doc.tag.split("}")[-1] != "ListBucketResult":
            raise ValueError("unexpected S3 listing")
        for entry in doc.findall("{*}Contents"):
            key = entry.findtext("{*}Key")
            name = key.rsplit("/", 1)[-1]
            match = re.fullmatch(
                r"glg_(tte|cspec|ctime)_([bn][0-9ab])_"
                + trig
                + r"_v\d+\.(fit|pha|rsp2?|fit\.gz)",
                name,
            )
            if not match:
                continue
            family, det, ext = match.groups()
            resource = (
                "detector_response"
                if ext.startswith("rsp")
                else ("photon_events" if family == "tte" else "binned_counts")
            )
            uri = base + url.quote(key)
            r = record(
                name,
                "Fermi/GBM " + det,
                "gamma",
                "burst",
                "product",
                resource,
                uri,
                name,
                uri=uri,
                level="locator",
                metadata={"bytes": int(entry.findtext("{*}Size"))},
            )
            r.update(association="confirmed", lineage=[trig + "/" + det])
            rows.append(r)
        if doc.findtext("{*}IsTruncated") != "true":
            return rows, False
        token = doc.findtext("{*}NextContinuationToken")
        if not token or token in seen:
            raise ValueError("invalid S3 continuation token")
        seen.add(token)


def alias_pattern(event):
    # Match complete designations; tolerate spaces, hyphens and underscores.
    words = []
    for alias in [event["id"], *event["aliases"]]:
        pieces = re.findall(r"[a-z]+|\d+|[^\W\d_]", alias.casefold())
        if pieces:
            words.append(r"[\s_\-]*".join(map(re.escape, pieces)))
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(words) + r")(?![a-z0-9])", re.I)


def gcn(event, cfg, get):
    pattern = alias_pattern(event)
    if cfg.get("path"):
        path = Path(cfg["base"]) / cfg["path"]
        data = path.read_bytes()
        get.receipts.append(
            {"local_archive": path.name, "response_sha256": digest(data)}
        )
    else:
        data = get.get(GCN_ARCHIVE)
    rows = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r|gz") as archive:
        for member in archive:
            if not member.isfile() or not member.name.endswith(".json"):
                continue
            item = json.load(archive.extractfile(member))
            reason = next(
                (
                    field
                    for field in ("eventId", "subject", "body")
                    if pattern.search(item.get(field) or "")
                ),
                None,
            )
            if reason:
                num = str(item["circularId"])
                rows.append(
                    record(
                        num,
                        "GCN",
                        "multimessenger",
                        "bulletin",
                        "notice",
                        "circular",
                        "https://gcn.nasa.gov/circulars/" + num,
                        item["subject"],
                        metadata={
                            "matched_field": reason,
                            "created_unix_ms": item.get("createdOn"),
                            "event_label": item.get("eventId"),
                        },
                    )
                )
    return rows, False


def tap(endpoint, query, cap, get):
    uri = (
        endpoint
        + "?"
        + url.urlencode(
            {
                "REQUEST": "doQuery",
                "LANG": "ADQL",
                "FORMAT": "votable",
                "MAXREC": cap + 1,
                "QUERY": query,
            }
        )
    )
    root = ET.fromstring(get.get(uri))
    statuses = root.findall(".//{*}INFO[@name='QUERY_STATUS']")
    if any(x.get("value") == "ERROR" for x in statuses):
        raise ValueError("; ".join(x.text or "TAP query failed" for x in statuses))
    table = root.find(".//{*}TABLE")
    data = table.find("./{*}DATA/{*}TABLEDATA") if table is not None else None
    if data is None:
        raise ValueError("TAP service did not supply a TABLEDATA VOTable")
    cols = [f.get("name").lower() for f in table.findall("{*}FIELD")]
    rows = [
        dict(zip(cols, [td.text or "" for td in tr.findall("{*}TD")], strict=True))
        for tr in data.findall("{*}TR")
    ]
    return rows[:cap], len(rows) > cap or any(
        i.get("value") == "OVERFLOW" for i in statuses
    )


def time_window(event):
    if not event["regions_deg"] or not event.get("utc"):
        raise Skip(
            "Needs UTC epoch and ICRS search cones; an unconverted sky map is insufficient"
        )
    epoch = utc(event["utc"]).timestamp() / 86400 + 40587
    return tuple(epoch + d for d in event["search_days"])


def mast(event, cfg, get):
    lo, hi = time_window(event)
    endpoint = cfg["url"]
    cap = cfg.get("limit", 500)
    rows = {}
    partial = False
    for ra, dec, radius in event["regions_deg"]:
        for page in range(1, cfg.get("pages", 20) + 1):
            request = {
                "service": "Mast.Caom.Cone",
                "params": {"ra": ra, "dec": dec, "radius": radius},
                "format": "json",
                "pagesize": cap,
                "page": page,
            }
            form = {"request": json.dumps(request)}
            for attempt in range(8):
                data = json.loads(get.get(endpoint, form))
                if data.get("status") != "EXECUTING":
                    break
                time.sleep(2)
            if data.get("status") != "COMPLETE":
                raise ValueError(
                    f"MAST {data.get('status')}: {data.get('msg', 'pending')}"
                )
            for row in data["data"]:
                if row.get("t_min") is None or row.get("t_max") is None:
                    continue
                if row["t_min"] > hi or row["t_max"] < lo:
                    continue
                uid = str(row["obsid"])
                r = record(
                    uid,
                    row.get("instrument_name")
                    or row.get("obs_collection")
                    or "unreported",
                    "archive",
                    "field overlap",
                    "product",
                    row.get("dataproduct_type") or "observation",
                    "https://mast.stsci.edu/portal/Mashup/Clients/Mast/Portal.html?searchQuery="
                    + url.quote(uid),
                    row.get("target_name") or uid,
                    level="locator",
                    metadata={
                        k: row.get(k)
                        for k in (
                            "obsid",
                            "obs_id",
                            "obs_collection",
                            "t_min",
                            "t_max",
                            "filters",
                            "s_region",
                        )
                    },
                )
                rows[uid] = r
            paging = data.get("paging", {})
            if page >= int(paging.get("pagesFiltered", paging.get("pages", 1))):
                break
        else:
            partial = True
    return list(rows.values()), partial


def obscore(event, cfg, get):
    lo, hi = time_window(event)
    cap = cfg.get("limit", 500)
    shapes = [
        f"INTERSECTS(s_region,CIRCLE('ICRS',{ra},{dec},{radius}))=1"
        for ra, dec, radius in event["regions_deg"]
    ]
    base = (
        f"SELECT TOP {cap + 1} obs_publisher_did,obs_id,obs_collection,instrument_name,target_name,"
        "dataproduct_type,access_url,t_min,t_max,em_min,em_max FROM ivoa.obscore "
        f"WHERE t_min<={hi} AND t_max>={lo} AND (" + " OR ".join(shapes) + ")"
    )
    items, after = [], None
    for page in range(cfg.get("pages", 20)):
        where = (
            ""
            if after is None
            else " AND obs_publisher_did > '" + after.replace("'", "''") + "'"
        )
        batch, partial = tap(
            cfg["url"], base + where + " ORDER BY obs_publisher_did", cap, get
        )
        items.extend(batch)
        if not partial or not batch or batch[-1]["obs_publisher_did"] == after:
            break
        after = batch[-1]["obs_publisher_did"]
    rows = []
    for item in items:
        pub = item["obs_publisher_did"]
        if not pub:
            raise ValueError("archive row lacks a publisher dataset identifier")
        rows.append(
            record(
                pub,
                item["instrument_name"] or item["obs_collection"] or "unreported",
                "archive",
                "field overlap",
                "product",
                item["dataproduct_type"] or "observation",
                cfg["url"],
                item["target_name"] or item["obs_id"],
                uri=item["access_url"],
                level="locator",
                metadata=item,
            )
        )
    return rows, partial


def crossref(event, cfg, get):
    pattern = alias_pattern(event)
    rows, partial = {}, False
    cap = cfg.get("limit", 100)
    for alias in [event["id"], *event["aliases"]]:
        uri = "https://api.crossref.org/works?" + url.urlencode(
            {
                "query.bibliographic": alias,
                "rows": cap,
                "select": "DOI,title,issued,URL",
            }
        )
        if rows:
            time.sleep(1)
        try:
            result = get.json(uri)["message"]
        except HTTPError as exc:
            if rows and exc.code == 429:
                return list(rows.values()), True
            raise
        partial |= result["total-results"] > cap
        for paper in result["items"]:
            title = " ".join(paper.get("title", []))
            if pattern.search(title):
                doi = paper["DOI"].lower()
                rows[doi] = record(
                    doi,
                    "Crossref",
                    "literature",
                    "bibliography",
                    "publication",
                    "paper",
                    "https://doi.org/" + doi,
                    title,
                    metadata={"issued": paper.get("issued")},
                )
    return list(rows.values()), partial


def arxiv(event, cfg, get):
    labels = [event["id"], *event["aliases"]]
    # Treat designations as phrases, excluding API query-language delimiters.
    phrases = [re.sub(r"[^\w .+-]", " ", value).strip() for value in labels]
    query = " OR ".join(f'all:"{term}"' for term in phrases if term)
    cap = cfg.get("limit", 100)
    uri = "https://export.arxiv.org/api/query?" + url.urlencode(
        {"search_query": query, "start": 0, "max_results": cap}
    )
    feed = ET.fromstring(get.get(uri))
    count = feed.findtext("{*}totalResults")
    if count is None:
        raise ValueError("arXiv response lacks a result count")
    rows = []
    pattern = alias_pattern(event)
    for entry in feed.findall("{*}entry"):
        title = " ".join(entry.findtext("{*}title", "").split())
        abstract = entry.findtext("{*}summary", "")
        paper = entry.findtext("{*}id", "").replace(
            "http://arxiv.org/", "https://arxiv.org/"
        )
        if not paper.startswith("https://arxiv.org/abs/"):
            raise ValueError("arXiv returned an invalid article identifier")
        if not pattern.search(title + " " + abstract):
            continue
        rows.append(
            record(
                paper.split("/abs/", 1)[1],
                "arXiv",
                "literature",
                "bibliography",
                "publication",
                "paper",
                paper,
                title,
                metadata={
                    "doi": entry.findtext("{*}doi"),
                    "published": entry.findtext("{*}published"),
                },
            )
        )
    return rows, int(count) > cap


def registry(get, cap=500):
    query = """SELECT DISTINCT access_url,ivoid
    FROM rr.interface NATURAL JOIN rr.capability NATURAL JOIN rr.res_detail
    WHERE standard_id LIKE 'ivo://ivoa.net/std/tap%' AND intf_role='std'
    AND detail_xpath='/capability/dataModel/@ivo-id'
    AND 1=ivo_nocasematch(detail_value,'ivo://ivoa.net/std/obscore%')"""
    rows, partial = tap("https://dc.g-vo.org/tap/sync", query, cap, get)
    return {
        "partial": partial,
        "sources": {
            "registry-" + digest(r["access_url"].encode())[:16]: {
                "adapter": "obscore",
                "url": r["access_url"].rstrip("/") + "/sync",
                "ivoid": r["ivoid"],
            }
            for r in rows
            if r["access_url"].startswith(("http://", "https://"))
        },
    }


ADAPTERS = {
    f.__name__: f
    for f in (
        curated,
        measurement_csv,
        gwosc,
        gracedb,
        fermi,
        gcn,
        mast,
        obscore,
        crossref,
        arxiv,
    )
}
