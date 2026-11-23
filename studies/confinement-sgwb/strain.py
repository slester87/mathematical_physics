"""GWOSC to pygwb one-sided CSD to an illustrative tensor Omega spectrum."""
import json

from bilby.gw.detector import get_empty_interferometer
from gwpy.timeseries import TimeSeries
import h5py
import numpy as np
from pygwb.orfs import calc_orf
from pygwb.spectral import cross_spectral_density
from scipy.signal import butter, csd as welch_csd, sosfiltfilt

from inputs import ROOT, STRAIN, fetch

START = 1126259446
FS = 4096
H0 = 67900 / 3.085677581491367e22


def load_offsource(detector):
    with h5py.File(fetch(STRAIN[detector]), "r") as h:
        ds = h["strain/Strain"]
        if ds.attrs["Xstart"] != START or ds.attrs["Xspacing"] != 1 / FS:
            raise ValueError("Unexpected strain coordinates")
        flags = [s.decode() for s in h["quality/simple/DQShortnames"][:]]
        mask = h["quality/simple/DQmask"][:14]
        for flag in ("DATA", "CBC_CAT1"):
            if not np.all(mask & (1 << flags.index(flag))):
                raise ValueError(f"Unusable {detector} interval: {flag}")
        samples = ds[:14 * FS]
    if not np.isfinite(samples).all():
        raise ValueError("Nonfinite strain")
    # Filter only the pre-event samples. Trim both filter boundaries.
    sos = butter(6, 16, btype="highpass", fs=FS, output="sos")
    clean = sosfiltfilt(sos, samples)[FS:-FS]
    return TimeSeries(clean, t0=START + 1, sample_rate=FS, unit="")


def main():
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    h, l = [load_offsource(ifo) for ifo in STRAIN]
    csd = cross_spectral_density(h, l, segment_duration=1, frequency_resolution=1,
                                 coarse_grain=False, overlap_factor=0, overlap_factor_welch=0)
    f = csd.frequencies.value
    use = (f >= 30) & (f <= 200)
    f, cross = f[use], np.real(csd.value[:, use])
    ref_f, ref_cross = welch_csd(h.value, l.value, fs=FS, window="hann", nperseg=FS, noverlap=0)
    target = ref_cross.real[np.searchsorted(ref_f, f)]
    difference = np.linalg.norm(cross.mean(axis=0)-target)/np.linalg.norm(target)
    if difference > .005:
        raise ValueError(f"Independent one-sided Welch CSD mismatch: {difference:.3g}")
    h1, l1 = [get_empty_interferometer(ifo) for ifo in STRAIN]
    gamma = calc_orf(f, h1.vertex, l1.vertex, h1.x, l1.x, h1.y, l1.y, polarization="tensor")
    keep = abs(gamma) > 0.1
    response = gamma[keep] * 3 * H0**2 / (10 * np.pi**2 * f[keep]**3)
    est = cross[:, keep] / response
    errors = est.std(axis=0, ddof=1) / np.sqrt(len(est))
    if len(est) < 5 or not np.all(np.isfinite(est)) or not np.all(errors > 0):
        raise ValueError("Invalid segment ensemble")
    np.savetxt(out / "strain_diagnostic.csv", np.c_[f[keep], est.mean(axis=0), errors],
               delimiter=",", header="frequency_Hz,Omega,empirical_standard_error", comments="")
    result = {"source": "GWOSC GW150914 LOSC 4 kHz V2, H1 x L1", "start_gps": START + 1,
              "end_gps_exclusive": START + 13, "nonoverlapping_segments": len(est),
              "welch_relative_L2_difference": float(difference), "bins": int(keep.sum()), "first_Hz": float(f[keep][0]), "last_Hz": float(f[keep][-1]),
              "median_bin_standard_error": float(np.median(errors))}
    (out / "strain.json").write_text(json.dumps(result, indent=2) + "\n")
    print(result)


if __name__ == "__main__":
    main()
