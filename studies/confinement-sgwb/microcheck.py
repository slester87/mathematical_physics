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
        command = ("import json,numpy as np,Plotter,DressedMasses;"
                   "DressedMasses.NUMBEROFPOINTS=150;"
                   f"r=Plotter.populateWrapper(*{args!r},3,3,True,2,'Normal');"
                   "print('RESULT '+json.dumps([None if x is None else float(x) for x in r]))")
        env = dict(os.environ, OPENBLAS_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1")
        log = subprocess.check_output([sys.executable,"-c",command],cwd=work,env=env,text=True)
        output = json.loads(next(line[7:] for line in log.splitlines() if line.startswith("RESULT ")))
    keys = ("Tn","Alpha","Beta","vwLTE","kappaLTE")
    reference = [float(archived[k]) for k in keys]
    current = [output[i] for i in (4,5,6,9,10)]
    f = np.geomspace(1e-4,1e4,32769)
    peaks = [float(spectrum(f,3,3,*params).max()) for params in [reference,current]]
    return {"upstream":REV,"inputs":dict(zip(("m2Sig","m2Eta","m2X","fPI"),args)),
            "archived":dict(zip(keys,reference)), "rerun":dict(zip(keys,current)),
            "h2Omega_peak_archived":peaks[0],"h2Omega_peak_rerun":peaks[1]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    report = run(parser.parse_args().checkout.resolve())
    out = ROOT/"results"
    out.mkdir(exist_ok=True)
    (out/"microcheck.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
