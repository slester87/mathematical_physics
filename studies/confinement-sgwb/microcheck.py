"""Rerun one archived SU(3), three-flavor grid cell with the pinned forward solver."""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import numpy as np
from inputs import GRIDS, ROOT, fetch
from study import spectrum

REV = "16785013ab2af982b053ddad9938c5a5283ea461"
MODULES = ("Plotter", "GravitationalWave", "Potential2", "DressedMasses", "WallVelocity",
           "WallVelocityLargeN", "config")


def run(checkout):
    args = (1e6,1e6,1e6,1102.27038425243)
    with fetch(GRIDS[3][0]).open() as stream:
        rows = csv.DictReader(stream)
        archived = next(r for r in rows if tuple(float(r[k]) for k in ("m2Sig","m2Eta","m2X","fPI")) == args)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        files = [name+".py" for name in MODULES] + ["IBData.csv","dIBData.csv","gstar_data.dat"]
        files += ["VGluonicData/VGluonicDataF3N3"+suffix+".csv" for suffix in ("","TTcs","mqTcs")]
        for name in files:
            raw = subprocess.check_output(["git","-C",str(checkout),"show",f"{REV}:{name}"])
            path = work/name
            path.parent.mkdir(exist_ok=True)
            if name.endswith(".py"):
                # Plotting/debug imports are unused with PLOT_RUN=False.
                source = re.sub(r"^(?:import matplotlib(?:\.pyplot as plt|\.colors)?|matplotlib\.use\(.+\)|from sympy import diff)[ \t]*$",
                                "",raw.decode(),flags=re.M)
                source = re.sub(r"^plt\.rcParams.*$","",source,flags=re.M)
                raw = source.replace("np.int(", "int(").encode()
            path.write_bytes(raw)
        # The upstream solver uses v=0 as a sentinel when no LTE wall is found.
        # Its efficiency routine divides by v at that sentinel. Preserve it
        # and skip the undefined efficiency calculation.
        command = f"""import json, Plotter, DressedMasses, WallVelocity
DressedMasses.NUMBEROFPOINTS = 150
original_kappa = WallVelocity.find_kappa
def kappa_if_moving(*args, vw=None):
    return 0.0 if vw == 0.0 else original_kappa(*args, vw=vw)
WallVelocity.find_kappa = kappa_if_moving
r = Plotter.populateWrapper(*{args!r}, 3, 3, True, 2, 'Normal')
print('RESULT ' + json.dumps([None if x is None else float(x) for x in r]))
"""
        env = dict(os.environ, OPENBLAS_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1")
        log = subprocess.check_output([sys.executable,"-c",command],cwd=work,env=env,text=True)
        output = json.loads(next(line[7:] for line in log.splitlines() if line.startswith("RESULT ")))
    keys = ("Tn","Alpha","Beta","vwLTE","kappaLTE")
    reference = [float(archived[k]) for k in keys]
    current = [output[i] for i in (4,5,6,9,10)]
    f = np.geomspace(1e-4,1e4,32769)
    if not all(v is not None and np.isfinite(v) and v > 0 for v in current[:3]):
        raise ValueError(f"Unresolved transition quantities: {current[:3]}")
    if any(v is None or not np.isfinite(v) or not 0 <= v <= 1 for v in current[3:]):
        raise ValueError(f"Invalid wall solution: {current[3:]}")
    peak_archived = float(spectrum(f,3,3,*reference).max())
    moving = all(v > 0 for v in current[3:])
    peak_rerun = float(spectrum(f,3,3,*current).max()) if moving else None
    return {"upstream":REV,"inputs":dict(zip(("m2Sig","m2Eta","m2X","fPI"),args)),
            "archived":dict(zip(keys,reference)), "rerun":dict(zip(keys,current)),
            "status":"positive_LTE" if moving else "no_positive_LTE_solution",
            "h2Omega_peak_archived":peak_archived,"h2Omega_peak_rerun":peak_rerun}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    report = run(parser.parse_args().checkout.resolve())
    out = ROOT/"results"
    out.mkdir(exist_ok=True)
    (out/"microcheck.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
