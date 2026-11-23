"""Versioned research inputs. Downloads are installed only after verification."""
import argparse
import hashlib
from pathlib import Path
import shutil
import tempfile
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "cache"
DCC = "https://dcc.ligo.org/public/0204/G2502630/001/"
RUNS = ("O1", "O2", "O3_HL", "O3_HV", "O3_LV", "O4a_HL")
PTA = "NANOGrav15yr_Sensitivity-Curves_v1.0.0.tar.gz"
SOURCES = {f"C_{r}.txt": (DCC + f"C_{r}.txt", None) for r in RUNS}
SOURCES[PTA] = ("https://zenodo.org/records/8092346/files/" + PTA + "?download=1",
                "5b7b0f424be2885f73fb058b28571b40")
GRIDS = {3: ("N3F3xi2_Normal_16Nov13hr.csv", "6b2cfb32d4ff8c6d7943024a2374493c59754236"),
         4: ("N4F3xi5_Normal_16Nov15hr.csv", "44295db1fe04590b532d038ff4e24cf73f3ea36d")}
for name, blob in GRIDS.values():
    SOURCES[name] = ("https://api.github.com/repos/miarobin/Eta-Prime-GWs/git/blobs/" + blob, None)
STRAIN = {}
for detector, checksum in [("H1", "50441a42c13fc1f14e5c4ea5527f1515"),
                           ("L1", "361ae6a040a9fef7897b1e0124d5b0a1")]:
    name = f"{detector[0]}-{detector}_LOSC_4_V2-1126259446-32.hdf5"
    STRAIN[detector] = name
    SOURCES[name] = ("https://gwosc.org/GW150914data/" + name, checksum)


def digest(path, algorithm):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def fetch(name):
    url, md5 = SOURCES[name]
    CACHE.mkdir(exist_ok=True)
    path = CACHE / name
    lock = ROOT / "data" / "sha256.txt"
    recorded = {n: h for h, n in (line.split() for line in lock.read_text().splitlines())} if lock.exists() else {}
    def verify(p):
        if md5 and digest(p, "md5") != md5:
            raise ValueError(f"Publisher checksum mismatch: {name}")
        sha = digest(p, "sha256")
        if name in recorded and sha != recorded[name]:
            raise ValueError(f"Pinned SHA-256 mismatch: {name}")
        return sha

    if path.exists():
        verify(path)
        return path
    with tempfile.NamedTemporaryFile(dir=CACHE, delete=False) as out:
        tmp = Path(out.name)
    try:
        request = Request(url, headers={"User-Agent": "SGWB-reproduction/1.0", "Accept": "application/vnd.github.raw+json" if "api.github.com/" in url else "*/*"})
        with urlopen(request, timeout=90) as source, tmp.open("wb") as out:
            shutil.copyfileobj(source, out)
        verify(tmp)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("group", choices=["limits", "strain", "pta"])
    group = parser.parse_args().group
    names = {"limits": [f"C_{r}.txt" for r in RUNS], "pta": [PTA], "strain": STRAIN.values()}[group]
    for name in names:
        print(digest(fetch(name), "sha256"), name, flush=True)
