"""Conditional prompt two-photon line limits from a common-source event."""
import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np
from numpy.polynomial.hermite import hermgauss

MPC_CM = 3.0856775814913673e24
YIELD_UNIT = 1e52
HERE = Path(__file__).resolve().parent


def number(x, *, positive=False, nonnegative=False):
    x = float(x)
    if not math.isfinite(x) or (positive and x <= 0) or (nonnegative and x < 0):
        raise ValueError(f"invalid numeric input: {x}")
    return x


def interval(values):
    low, high = map(number, values)
    if high <= low:
        raise ValueError(f"empty interval: {values}")
    return low, high


def records(path, fields, event_id=None):
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = set(fields)
        if event_id is not None:
            required.add("event_id")
        if not required.issubset(reader.fieldnames or ()):
            raise ValueError(f"{path} needs columns {sorted(required)}")
        for row in reader:
            if event_id is not None and row["event_id"] != event_id:
                raise ValueError(f"{path} contains data for a different event")
            yield row


def source_distribution(path, host, event_id):
    """Update joint GW-only (D_L,z) weights with one independent host spectrum."""
    distance, z, weights = [], [], []
    for row in records(path, ("distance_Mpc", "z", "weight"), event_id):
        distance.append(number(row["distance_Mpc"], positive=True))
        z.append(number(row["z"], nonnegative=True))
        weights.append(number(row["weight"], nonnegative=True))
    if not any(weights):
        raise ValueError("GW source distribution has no positive weight")
    supported = np.array(weights) > 0
    distance, z, weights = (np.asarray(v)[supported] for v in (distance, z, weights))
    rest = number(host["rest_um"], positive=True)
    observed = number(host["centroid_um"], positive=True)
    error = number(host["sigma_um"], positive=True)
    residual = (rest * (1 + z) - observed) / error
    logw = np.log(weights) - 0.5 * residual**2
    if not np.any(np.isfinite(logw)):
        raise ValueError("host likelihood could not be evaluated on the supplied samples")
    weights = np.exp(logw - logw.max())
    return distance, z, weights / weights.sum()


def count_photons(path, sensor, event_id):
    t0, t1 = interval(sensor["time_s"])
    e0, e1 = interval(sensor["count_window_MeV"])
    live_start, live_end = interval(sensor["continuous_live_interval_s"])
    if not live_start <= t0 < t1 <= live_end:
        raise ValueError("count window lacks continuous sensor exposure")
    seen = set()
    count = 0
    for row in records(path, ("photon_id", "dt_s", "energy_MeV"), event_id):
        identity = row["photon_id"].strip()
        if not identity or identity in seen:
            raise ValueError(f"missing or duplicate photon ID: {identity!r}")
        seen.add(identity)
        t = number(row["dt_s"])
        e = number(row["energy_MeV"], nonnegative=True)
        count += int(t0 <= t < t1 and e0 <= e < e1)
    return count


def window_probability(mean, low, high, width):
    # Difference of normal survival functions on the nearer tail avoids
    # catastrophic cancellation for a narrow window above or below the line.
    lo, hi = (low - mean) / (math.sqrt(2) * width), (high - mean) / (math.sqrt(2) * width)
    if lo >= 0:
        return 0.5 * (math.erfc(lo) - math.erfc(hi))
    return 0.5 * (math.erfc(-hi) - math.erfc(-lo))


def read_window_area(path, window):
    """Area after redistribution into the declared measured-energy window."""
    true_energy, area = [], []
    cols = ("true_energy_MeV", "window_low_MeV", "window_high_MeV", "area_cm2")
    for row in records(path, cols):
        if interval([row["window_low_MeV"], row["window_high_MeV"]]) != window:
            raise ValueError("tabulated area belongs to a different count window")
        true_energy.append(number(row["true_energy_MeV"], positive=True))
        area.append(number(row["area_cm2"], nonnegative=True))
    if len(area) < 2 or np.any(np.diff(true_energy) <= 0):
        raise ValueError("tabulated response needs increasing true energies")
    return true_energy, area


def response(source, sensor, ratio, error, scale, order, area_table=None):
    distance, z, sw = source
    nodes, mw = hermgauss(order)
    masses = scale * (ratio + math.sqrt(2) * error * nodes)
    if np.any(masses <= 0):
        raise ValueError("mass quadrature crosses zero; supply a positive mass model")
    energy = masses[None, :] / (2 * (1 + z[:, None]))
    if area_table is None:
        emin, emax = interval(sensor["true_band_MeV"])
        low, high = interval(sensor["count_window_MeV"])
        width = number(sensor["resolution_sigma_MeV"], positive=True)
        area = number(sensor["effective_area_cm2"], nonnegative=True)
        in_window = [window_probability(e, low, high, width) if emin <= e < emax else 0.0
                     for e in energy.flat]
        window_area = area * np.array(in_window).reshape(energy.shape)
    else:
        window_area = np.interp(energy, *area_table, left=0.0, right=0.0)
    # Integrated photon NUMBER fluence uses transverse comoving distance D_L/(1+z).
    fluence = YIELD_UNIT / (4 * math.pi * (MPC_CM * distance / (1 + z))**2)
    weights = sw[:, None] * mw[None, :] / math.sqrt(math.pi)
    return (fluence[:, None] * window_area).ravel(), weights.ravel(), float(np.sum(weights * energy))


def poisson_lower(n, mean):
    """P(K <= n) for each mean, including zero, summed in log space."""
    with np.errstate(divide="ignore"):
        logmean = np.log(mean)
    term = np.zeros_like(mean, dtype=float)
    total = term.copy()
    for k in range(1, n + 1):
        term = term + logmean - math.log(k)
        total = np.logaddexp(total, term)
    return np.exp(np.minimum(0, total - mean))


def limits(n, background, rate, weights, yield_units, max_units, alpha):
    """Invert the conditional mixture lower-tail test in emitted-photon units."""
    def tail(y):
        return float(weights @ poisson_lower(n, background + y * rate))

    prob = tail(yield_units)
    if tail(0) <= alpha:
        return prob, None, "background_tension", "background_tension"
    status = "excluded_point" if prob <= alpha else "retained_point"
    if tail(max_units) > alpha:
        return prob, None, status, "above_scan_max"
    lo, hi = 0.0, min(1., max_units)
    while tail(hi) > alpha:
        lo, hi = hi, min(2 * hi, max_units)
    if lo == 0:
        while hi > 0 and tail(hi / 2) <= alpha:
            hi /= 2
        lo = hi / 2
    for _ in range(55):
        mid = (lo + hi) / 2
        if tail(mid) > alpha:
            lo = mid
        else:
            hi = mid
    return prob, hi * YIELD_UNIT, status, "bounded"


def analyze(event_path, lattice_path, order=48):
    if not 2 <= order <= 100:
        raise ValueError("quadrature order must be between 2 and 100")
    event = json.loads(event_path.read_text(encoding="utf-8"))
    if event["data_kind"] not in {"synthetic", "observed"} or not event["association"].strip():
        raise ValueError("declare the origin and evidence for the common-source association")
    sensor, scan = event["sensor"], event["scan"]
    source = source_distribution(event_path.parent / event["gw"]["samples"], event["host"], event["event_id"])
    count = count_photons(event_path.parent / sensor["photons"], sensor, event["event_id"])
    area_table = None
    if "window_area_csv" in sensor:
        area_table = read_window_area(event_path.parent / sensor["window_area_csv"],
                                      interval(sensor["count_window_MeV"]))
    b = number(sensor["mean_background_counts"], nonnegative=True)
    y = number(scan["photons_emitted"], nonnegative=True)
    max_y = number(scan["max_photons"], positive=True)
    if y > max_y:
        raise ValueError("benchmark yield exceeds scan range")
    alpha = number(scan["alpha"], positive=True)
    if alpha >= 1:
        raise ValueError("alpha must be below one")
    for lattice in records(lattice_path, ("gauge_group", "scalar_mass_over_sqrt_sigma", "standard_error")):
        ratio = number(lattice["scalar_mass_over_sqrt_sigma"], positive=True)
        err = number(lattice["standard_error"], nonnegative=True)
        for value in scan["sqrt_string_tension_MeV"]:
            scale = number(value, positive=True)
            rates, weights, energy = response(source, sensor, ratio, err, scale, order, area_table)
            p, upper, status, limit_status = limits(count, b, rates, weights, y / YIELD_UNIT, max_y / YIELD_UNIT, alpha)
            yield dict(event_id=event["event_id"], data_kind=event["data_kind"],
                       group=lattice["gauge_group"], sqrt_sigma_MeV=scale,
                       line_energy_MeV=energy, n_observed=count, background=b,
                       photons_emitted=y, mean_signal_counts=float(weights @ rates) * y / YIELD_UNIT,
                       lower_tail=p, alpha=alpha, upper_photons=upper, max_photons=max_y,
                       limit_status=limit_status, status=status)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event", type=Path)
    parser.add_argument("--lattice", type=Path, default=HERE / "lattice.csv")
    parser.add_argument("--order", type=int, default=48, help="Gauss-Hermite order for lattice uncertainty")
    args = parser.parse_args()
    try:
        rows = list(analyze(args.event, args.lattice, args.order))
        if not rows:
            raise ValueError("no candidate points")
    except (ValueError, ArithmeticError, OSError, KeyError) as exc:
        parser.exit(2, f"{parser.prog}: {exc}\n")
    out = csv.DictWriter(sys.stdout, fieldnames=rows[0], lineterminator="\n")
    out.writeheader()
    out.writerows(rows)


if __name__ == "__main__":
    main()
