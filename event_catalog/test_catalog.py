import csv
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from event_catalog import archives
from event_catalog.model import ROOT, comparisons, digest, requirements, validate_event
from event_catalog.store import connect, dossier, sync

EX = ROOT / "examples"
THEORY = json.loads((ROOT / "theories/prompt-glueball.json").read_text())


class MockReader(archives.Reader):
    def __init__(self, responses):
        super().__init__()
        self.responses = iter(responses)
        self.requests = []

    def get(self, uri):
        self.requests.append(uri)
        payload = next(self.responses)
        if isinstance(payload, Exception):
            raise payload
        if isinstance(payload, dict):
            payload = json.dumps(payload).encode()
        self.receipts.append({"url": uri, "response_sha256": digest(payload)})
        return payload


class EventCatalogTests(unittest.TestCase):
    def setUp(self):
        self.db = connect(":memory:")
        self.addCleanup(self.db.close)
        self.gw = json.loads((EX / "GW170817.json").read_text())
        self.sn = json.loads((EX / "SN1987A.json").read_text())

    def test_messengers_kept_separate_and_alias(self):
        for e in (self.gw, self.sn):
            sync(self.db, e, EX, ["reviewed"])
        gw = dossier(self.db, "AT 2017gfo", THEORY)
        self.assertEqual(len(gw["evidence"]), 16)
        self.assertEqual(len(gw["corroboration"]), 2)
        self.assertEqual(
            sum(bool(r["usable"]) for r in gw["theory"]["requirements"]), 1
        )
        self.assertFalse(gw["theory"]["inputs_complete"])
        self.assertEqual(
            dossier(self.db, "SN 1987A")["corroboration"][0]["subject"],
            "supernova neutrino burst",
        )
        self.assertEqual(gw["coverage"]["fermi"]["status"], "unqueried")

    def test_future_event_without_position_or_gw(self):
        future = dict(
            self.sn,
            id="FUTURE-TEST",
            origin="synthetic",
            status="provisional",
            aliases=["TEST-2999A"],
            utc=None,
            regions_deg=[],
            evidence=[],
        )
        log = sync(
            self.db,
            future,
            EX,
            ["reviewed", "gwosc", "gracedb", "fermi", "mast", "eso"],
        )
        self.assertEqual([x["status"] for x in log], ["empty"] + ["missing_input"] * 5)
        self.assertEqual(dossier(self.db, "TEST-2999A")["evidence"], [])
        future["regions_deg"] = [[400, 1, 1]]
        with self.assertRaises(ValueError):
            validate_event(future)

    def test_retries_revisions_duplicates_and_failed_archive(self):
        r = self.gw["evidence"][0]
        adapter = archives.ADAPTERS["curated"]

        def do(rows):
            with patch.dict(archives.ADAPTERS, curated=lambda *args: (rows, False)):
                return sync(self.db, self.gw, EX, ["reviewed"])[0]["status"]

        self.assertEqual(do([r, r]), "returned")
        self.assertEqual(do([r]), "returned")
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM batches").fetchone()[0], 1
        )
        self.assertEqual(
            do([r, dict(r, description="incompatible duplicate")]), "failed"
        )
        report = dossier(self.db, "GW170817")
        self.assertTrue(report["evidence"][0]["stale"])
        self.assertEqual(do([]), "empty")
        self.assertFalse(dossier(self.db, "GW170817")["evidence"])
        self.assertIs(adapter, archives.ADAPTERS["curated"])

    def test_checksummed_file_and_event_retraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data.csv").write_text("123")
            r = dict(
                self.gw["evidence"][0],
                kind="product",
                resource="distance_samples",
                level="checked_file",
                file="data.csv",
                sha256=digest(b"123"),
            )
            e = dict(self.gw, evidence=[r])
            contract = {
                "name": "test",
                "requires": [
                    {
                        "id": "distance",
                        "level": "checked_file",
                        "match": {"resource": "distance_samples"},
                    }
                ],
            }
            sync(self.db, e, root, ["reviewed"])
            self.assertTrue(
                dossier(self.db, e["id"], contract)["theory"]["inputs_complete"]
            )
            (root / "data.csv").write_text("changed")
            self.assertEqual(
                sync(self.db, e, root, ["reviewed"])[0]["status"], "failed"
            )
            self.assertFalse(
                dossier(self.db, e["id"], contract)["theory"]["inputs_complete"]
            )
            (root / "data.csv").write_text("123")
            sync(self.db, dict(e, status="retracted"), root, ["reviewed"])
            self.assertFalse(
                dossier(self.db, e["id"], contract)["theory"]["inputs_complete"]
            )

    def test_sensor_window_lineage_and_association(self):
        contract = {
            "name": "x",
            "requires": [
                {
                    "id": k,
                    "level": "checked_file",
                    "same_sensor": "g",
                    "match": {"resource": k},
                    "covers": {"time_s": [0, 2]},
                }
                for k in ("counts", "response")
            ],
        }
        base = dict(
            self.gw["evidence"][0],
            association="confirmed",
            kind="product",
            level="checked_file",
            stale=False,
            id="a",
            sensor="A",
            time_s=[-1, 3],
            resource="counts",
        )
        other = dict(base, id="b", resource="response", sensor="B")
        for changes in (
            {},
            {"sensor": "A", "time_s": [0, 1]},
            {"sensor": "A", "association": "candidate"},
        ):
            self.assertFalse(
                requirements([base, dict(other, **changes)], contract, self.gw)[
                    "inputs_complete"
                ]
            )
        self.assertTrue(
            requirements([base, dict(other, sensor="A")], contract, self.gw)[
                "inputs_complete"
            ]
        )
        base.update(
            kind="measurement",
            value=5,
            unit="s",
            sigma=1,
            uncertainty="gaussian_1sigma",
            comparison_key="same",
        )
        b = dict(base, id="b", sensor="B", value=7)
        self.assertEqual(comparisons([base, b]), [])
        self.assertAlmostEqual(
            comparisons([base, dict(b, lineage=["independent"])])[0][
                "difference_sigma"
            ],
            -(2**0.5),
        )

    def test_global_circulars_and_false_alias(self):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w:gz") as t:
            for i, subject in enumerate(
                ["LIGO/Virgo G298048 follow-up", "Context GW1708170"]
            ):
                raw = json.dumps(
                    dict(circularId=i, subject=subject, eventId="Other", body="")
                ).encode()
                entry = tarfile.TarInfo(f"{i}.json")
                entry.size = len(raw)
                t.addfile(entry, io.BytesIO(raw))
        rows, _ = archives.gcn(self.gw, {}, MockReader([data.getvalue()]))
        self.assertEqual([r["key"] for r in rows], ["0"])
        self.assertEqual(rows[0]["association"], "candidate")

    def test_tabular_sensor_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sensor.csv"
            with p.open("w") as f:
                w = csv.writer(f)
                w.writerows(
                    [["event", "row", "flux"], ["SN1987A", "1", 12], ["Other", "2", 11]]
                )
            seed = self.sn["evidence"][0]
            cfg = dict(
                base=tmp,
                path=p.name,
                select={"event": "SN1987A"},
                defaults=seed,
                columns={"key": "row", "value": "flux"},
            )
            rows, _ = archives.measurement_csv(self.sn, cfg, MockReader([]))
            self.assertEqual([(r["key"], r["value"]) for r in rows], [("1", 12)])

    def test_obscore_overlap_overflow_and_error(self):
        fields = "obs_publisher_did instrument_name target_name obs_collection dataproduct_type access_url obs_id".split()
        table = (
            "<TABLE>"
            + "".join(f'<FIELD name="{f}"/>' for f in fields)
            + "<DATA><TABLEDATA><TR>"
            + "".join(
                f"<TD>{v}</TD>"
                for v in ("ivo://1", "new camera", "elsewhere", "", "image", "", "1")
            )
            + "</TR></TABLEDATA></DATA></TABLE>"
        )
        data = (
            "<VOTABLE><RESOURCE>"
            + table
            + '<INFO name="QUERY_STATUS" value="OVERFLOW"/></RESOURCE></VOTABLE>'
        ).encode()
        fetch = MockReader([data])
        rows, partial = archives.obscore(
            self.gw, {"url": "https://test.invalid/sync"}, fetch
        )
        self.assertTrue(partial)
        query = parse_qs(urlparse(fetch.requests[0]).query)["QUERY"][0]
        self.assertIn("INTERSECTS(s_region", query)
        self.assertIn("t_max>=", query)
        self.assertEqual(rows[0]["association"], "candidate")
        with self.assertRaisesRegex(ValueError, "bad query"):
            archives.tap(
                "https://test.invalid",
                "x",
                1,
                MockReader(
                    [b'<a><INFO name="QUERY_STATUS" value="ERROR">bad query</INFO></a>']
                ),
            )

    def test_fermi_pagination_and_gwosc_identity(self):
        prefix = "fermi/data/gbm/triggers/2017/bn170817529/current/"

        def page(name, tail):
            return (
                "<ListBucketResult><Contents><Key>"
                + prefix
                + name
                + "</Key><Size>22</Size></Contents>"
                + tail
                + "</ListBucketResult>"
            ).encode()

        fetch = MockReader(
            [
                page(
                    "glg_tte_b0_bn170817529_v00.fit",
                    "<IsTruncated>true</IsTruncated><NextContinuationToken>x</NextContinuationToken>",
                ),
                page(
                    "glg_cspec_b0_bn170817529_v00.rsp2",
                    "<IsTruncated>false</IsTruncated>",
                ),
            ]
        )
        rows, _ = archives.fermi(self.gw, {}, fetch)
        self.assertEqual(
            [r["resource"] for r in rows], ["photon_events", "detector_response"]
        )
        self.assertIn("continuation-token=x", fetch.requests[-1])
        with self.assertRaisesRegex(ValueError, "another event"):
            archives.gwosc(self.gw, {}, MockReader([{"name": "wrong", "version": 3}]))


if __name__ == "__main__":
    unittest.main()
