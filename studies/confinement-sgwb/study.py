"""Conditional prior robustness and cross-band reach for confinement spectra."""
from __future__ import annotations
import csv
import hashlib
import io
import json
from pathlib import Path
import tarfile

import numpy as np
from inputs import CACHE, GRIDS, PTA, ROOT, RUNS, fetch

YEAR = 365.25 * 86400
H100 = 100000 / 3.085677581491367e22
H_LVK = .679
PTA_MEMBER = "sensitivity_curves/sensitivity_curves_NG15yr_fullPTA.txt"
PTA_HASH = "363bb8aabd76f0973d3075cfa7a4f83bd9ae91e0a104d6d53bcdfe507da29544"
AXES = ("m2Sig", "m2Eta", "m2X", "fPI")
trap = np.trapezoid if hasattr(np, "trapezoid") else np.trapz


def spectrum(f, n, flavors, temperature, alpha, beta, wall, efficiency):
    """Present-day h² Omega, finite-lived acoustic source plus turbulence."""
    g = 106.75 + 2 * (n*n - 1) + 3.5*n*flavors
    w = (g / 100)**(1/6) * temperature / 100
    r = wall / beta
    q = efficiency * alpha / (1 + alpha)
    x = f * r / (8.876e-6*w)
    y = f * r / (27e-6*w)
    life = min(1., (8*np.pi)**(1/3)*r / np.sqrt(.75*q))
    sound = 2.59e-6 * .678**2 * q*q * life * x**3 * (7/(4+3*x*x))**3.5
    turb = 3.35e-4*(.05*q)**1.5 * y**3 / ((1+y)**(11/3)*(1+8*np.pi*f/(16.6e-6*w)))
    return r*(100/g)**(1/3)*(sound+turb)


def lvk():
    """Compress independent observations on the declared 1/32 Hz grid."""
    runs = []
    for run in RUNS:
        table = np.loadtxt(fetch(f"C_{run}.txt"))
        f, c, sigma = table[:, :3].T
        keep = np.isfinite(sigma) & (sigma > 0) & np.isfinite(c)
        if table.shape[1] == 4:
            mask = table[:, 3]
            if not np.isin(mask, [0, 1]).all():
                raise ValueError(f"Unexpected mask: {run}")
            keep &= mask.astype(bool)
        indices = np.rint(32*f).astype(int)
        if not np.all(np.diff(indices) == 1) or max(abs(indices/32-f)) > .00051:
            raise ValueError(f"Unexpected frequency grid: {run}")
        runs.append((indices[keep], c[keep], sigma[keep]))
    length = max(i.max() for i, _, _ in runs) + 1
    precision, score = np.zeros(length), np.zeros(length)
    for i, c, sigma in runs:
        precision[i] += 1/sigma**2
        score[i] += c/sigma**2
    use = precision > 0
    return np.flatnonzero(use)/32, score[use]/precision[use], 1/np.sqrt(precision[use]), runs


def pta():
    unpacked = CACHE / Path(PTA_MEMBER).name
    if unpacked.exists():
        buf = unpacked.read_bytes()
    else:
        with tarfile.open(fetch(PTA), "r:gz") as archive:
            buf = archive.extractfile(PTA_MEMBER).read()
    if hashlib.sha256(buf).hexdigest() != PTA_HASH:
        raise ValueError("PTA table checksum mismatch")
    f, hc, seff, omega = np.loadtxt(io.BytesIO(buf), delimiter=",").T
    np.testing.assert_allclose(hc**2/f, seff, rtol=1e-8)
    np.testing.assert_allclose(2*np.pi**2/3 * (f/H100)**2*hc**2, omega*.674**2, rtol=.001)
    use = f >= 1/(15*YEAR)
    return f[use], omega[use]*.674**2


def lisa(f):
    """Smith & Caldwell eqs. 53, 54, 59, 63. Output is h² Sigma_Omega."""
    acceleration = 5.76e-48*(1+(.0004/f)**2)
    optical = 3.6e-41
    transfer = 299792458/(2*np.pi*2.5e9)
    intensity = np.sqrt(2)*20/3*(acceleration/(2*np.pi*f)**4 + optical)*(1+(3*f/(4*transfer))**2)
    return 4*np.pi**2*f**3*intensity/(3*H100**2)


def prior_weights(rows, cells, kind):
    """Exact cell volumes of a uniform or log-uniform product measure."""
    weights = np.ones(len(rows))
    for name in AXES:
        nodes = cells[name]
        edges = np.r_[nodes[0], (nodes[1:]+nodes[:-1])/2, nodes[-1]]
        width = np.diff(edges if kind == "linear" else np.log(edges))
        weights *= width[np.searchsorted(nodes, rows[name])]
    return weights / weights.sum()


def q95(x, w):
    idx = np.argsort(x)
    return float(x[idx[np.searchsorted(np.cumsum(w[idx]), .95)]])


def integral_snr(f, sig, noise, duration):
    return float(np.sqrt(duration*trap((sig/noise)**2, f)))


def gaussian_ul(score, precision, prior):
    x = np.geomspace(1e-13, 1e-6, 40001)
    density = np.exp(score*x - .5*precision*x*x)
    if prior == "log":
        density /= x
    mass = np.r_[0, np.cumsum(.5*(density[1:]+density[:-1])*np.diff(x))]
    return float(np.interp(.95*mass[-1], mass, x))


def evaluate():
    f, c, sigma, runs = lvk()
    w = 1/sigma**2
    data_score = c*w
    cbc = (f/25)**(2/3)
    # Fixed compact-binary power law, positive amplitude b at 25 Hz.
    # Midpoint quadrature in log(b), normalized relative to CBC-only.
    log_edges = np.linspace(np.log(1e-13), np.log(1e-6), 2049)
    b = np.exp((log_edges[:-1]+log_edges[1:])/2)
    base_log = b*np.sum(cbc*data_score) - .5*b*b*np.sum(cbc*cbc*w)
    cbc_p = np.exp(base_log-base_log.max())
    cbc_p /= cbc_p.sum()
    fp, np_ = pta()
    fl = np.geomspace(1e-4, .1, 4097)
    nl = lisa(fl)
    peak_grid = np.geomspace(1e-5, 1e4, 8193)
    controls = []
    for slope, published in [(0,(8.6e-9,2.8e-9)),(2/3,(6.3e-9,2e-9)),(3,(1e-9,3.2e-10))]:
        shape = (f/25)**slope
        score, prec = np.sum(shape*data_score), np.sum(shape**2*w)
        controls.append(dict(slope=slope, estimate=score/prec, sigma=prec**-.5,
                             q95_linear=gaussian_ul(score,prec,"linear"), q95_log=gaussian_ul(score,prec,"log"),
                             published_linear=published[0], published_log=published[1]))

    def measure(n, flavors, params):
        def h2(freq):
            return spectrum(freq, n, flavors, *params)
        lv = h2(f)/H_LVK**2
        rho = float(np.sqrt(np.sum(lv*lv*w)))
        ratio = float(np.sum(lv*data_score) - .5*rho**2)
        cross = np.sum(lv*cbc*w)
        # Retain sub-epsilon differences against the shared foreground model.
        marginalized = ratio + np.log1p(np.sum(cbc_p*np.expm1(-b*cross)))
        peak = h2(peak_grid)
        j = int(np.argmax(peak))
        return dict(peak_Hz=float(peak_grid[j]), peak_h2Omega=float(peak[j]), lvk_snr=rho,
                    pta_snr=integral_snr(fp,h2(fp),np_,2*15*YEAR),
                    lisa_snr=integral_snr(fl,h2(fl),nl,4*YEAR),
                    logL_vs_noise=ratio, logL_with_CBC_vs_CBC=float(marginalized))

    bench = json.loads((ROOT/"data/benchmark.json").read_text())
    params = [bench[k] for k in ("Tp","alpha","betaH","vw","kappa")]
    reference = measure(3, 6, params)
    logf, logo = np.loadtxt(ROOT/"data/figure7.csv", delimiter=",", skiprows=1).T
    residual = spectrum(10**logf,3,6,*params)/10**logo - 1
    reference["fig7_max_relative_difference"] = float(np.max(abs(residual)))
    outputs, summaries, counts = [], [], {}
    for n, (name, _) in GRIDS.items():
        grid = np.genfromtxt(fetch(name), delimiter=",", names=True)
        axes = {k: np.unique(grid[k]) for k in AXES}
        coords = np.column_stack([grid[k] for k in AXES])
        if len(grid) != np.prod([len(a) for a in axes.values()]) or len(np.unique(coords,axis=0)) != len(grid):
            raise ValueError("Incomplete or duplicated grid")
        therm = ("Tn","Alpha","Beta","vwLTE","kappaLTE")
        active = np.ones(len(grid), dtype=bool)
        for key in therm:
            active &= np.isfinite(grid[key]) & (grid[key] > 0)
        active &= (grid["vwLTE"] <= 1) & (grid["kappaLTE"] <= 1)
        keep = active & (grid["Message"] >= .90) & (grid["Message"] <= 1)
        rows = grid[keep]
        counts[str(n)] = dict(total=len(grid),positive_LTE=int(active.sum()),retained=len(rows),fully_perturbative=int(np.sum(keep & (grid["Message"] == 1))))
        points = [measure(n,3,[row[k] for k in therm]) for row in rows]
        ll = np.array([p["logL_with_CBC_vs_CBC"] for p in points])
        peaks = np.array([p["peak_h2Omega"] for p in points])
        for row, point in zip(rows, points):
            point.update({"N":n, **{k:float(row[k]) for k in (*AXES, *therm, "Message")}})
        outputs.extend(points)
        for kind in ("linear","log"):
            weights = prior_weights(rows, axes, kind)
            for support, mask in [("full", np.ones(len(rows), dtype=bool)),
                                  ("lower_eta", rows["m2Eta"] <= axes["m2Eta"][2])]:
                p = weights[mask] / np.sum(weights[mask])
                centered = ll[mask] - np.max(ll[mask])
                change = np.expm1(centered)
                mean_change = np.sum(p*change)
                relative_update = (change-mean_change)/(1+mean_change)
                post = p*(1+relative_update)
                if support == "full":
                    for point, weight, updated in zip(points, p, post):
                        point[kind+"_prior_mass"] = float(weight)
                        point[kind+"_posterior_mass"] = float(updated)
                summaries.append(dict(N=n,prior=kind,support=support,points=int(mask.sum()),
                                      prior_peak_q95=q95(peaks[mask],p),post_peak_q95=q95(peaks[mask],post),
                                      total_variation=float(np.sum(p*abs(relative_update))/2),
                                      delta_logL=float(np.ptp(ll[mask]))))
    return ({"valid_baseline_bins":sum(len(i) for i,_,_ in runs),"network_bins":len(f),
             "counts":counts,"power_law_controls":controls,"benchmark":reference,
             "lisa_flat_5sigma_h2Omega":5/integral_snr(fl,np.ones_like(fl),nl,4*YEAR),
             "reach_max":{k:max(p[k] for p in outputs) for k in ["lvk_snr","pta_snr","lisa_snr"]},
             "priors":summaries}, outputs)


def main():
    report, points = evaluate()
    out = ROOT/"results"
    out.mkdir(exist_ok=True)
    with (out/"points.csv").open("w",newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=points[0])
        writer.writeheader()
        writer.writerows(points)
    serialized = json.dumps(report,indent=2,allow_nan=False)
    (out/"inference.json").write_text(serialized+"\n")
    print(serialized)


if __name__ == "__main__":
    main()
