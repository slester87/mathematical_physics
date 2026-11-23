"""Independent numerical checks on public data, analytic controls and injections."""
import json
from math import fsum, sqrt
from statistics import NormalDist

import numpy as np
from study import (H_LVK, ROOT, YEAR, evaluate, gaussian_ul, integral_snr,
                   lisa, lvk, spectrum)


def main():
    report, points = evaluate()
    f, c, sigma, runs = lvk()
    # Truncated-normal CDF for the uniform-prior scale-invariant control.
    flat = report["power_law_controls"][0]
    mu, sd = flat["estimate"], flat["sigma"]
    gaussian = NormalDist(mu, sd)
    c0, c1 = gaussian.cdf(1e-13), gaussian.cdf(1e-6)
    exact = gaussian.inv_cdf(c0+.95*(c1-c0))
    np.testing.assert_allclose(gaussian_ul(mu/sd**2,1/sd**2,"linear"),exact,rtol=2e-7)

    # Independently sum each baseline before any network compression.
    params = json.loads((ROOT/"data/benchmark.json").read_text())
    args = [params[k] for k in ("Tp","alpha","betaH","vw","kappa")]
    def template(freq):
        return spectrum(freq, 3, 6, *args)/H_LVK**2
    rho2, score = 0., 0.
    for index, values, noise in runs:
        h = template(index/32.)
        rho2 += fsum((h/noise)**2)
        score += fsum(h*values/noise**2)
    bench = report["benchmark"]
    np.testing.assert_allclose([sqrt(rho2),score-.5*rho2],
                               [bench["lvk_snr"],bench["logL_vs_noise"]],rtol=2e-12)

    # Add a five-sigma template to the real cross correlations. The fitted
    # amplitude must shift by exactly five of its own uncertainty units.
    h = template(f)
    inj = 5/sqrt(rho2)
    new_score = fsum(h*(c+inj*h)/sigma**2)
    shift = (new_score-score)/sqrt(rho2)
    np.testing.assert_allclose(shift,5,rtol=1e-12)

    # Reference calculation for the CBC integral uses Gauss-Legendre nodes,
    # in place of the production midpoint rule. Average the likelihood *ratio*
    # against the normalized foreground-only posterior for numerical stability.
    x, quad_w = np.polynomial.legendre.leggauss(96)
    b = np.exp(np.log(10)*(-9.5+3.5*x))
    g = (f/25)**(2/3)/sigma
    ell = b*fsum(g*c/sigma)-.5*b*b*fsum(g*g)
    weights = quad_w*np.exp(ell-ell.max())
    cross = fsum(h*g/sigma)
    delta = score-.5*rho2 + np.log1p(np.average(np.expm1(-b*cross),weights=weights))
    np.testing.assert_allclose(delta,bench["logL_with_CBC_vs_CBC"],rtol=2e-5)

    fl = np.geomspace(1e-4,.1,8193)
    refined = integral_snr(fl,template(fl)*H_LVK**2,lisa(fl),4*YEAR)
    np.testing.assert_allclose(refined,bench["lisa_snr"],rtol=2e-5)
    np.testing.assert_allclose(report["lisa_flat_5sigma_h2Omega"],2.1e-13,rtol=.05)
    if bench["fig7_max_relative_difference"] >= .07:
        raise ValueError("Published Figure 7 curve differs by more than 7%")
    for control in report["power_law_controls"]:
        for prior in ("linear","log"):
            np.testing.assert_allclose(control["q95_"+prior], control["published_"+prior], rtol=.08)
    for p in report["priors"]:
        # Sharp distribution-free bound when log likelihood oscillates by d.
        if p["total_variation"] > np.tanh(p["delta_logL"]/4) + 1e-17:
            raise ValueError("Posterior variation exceeds likelihood-ratio bound")
    for n in (3,4):
        subset = [p for p in points if p["N"] == n]
        for kind in ("linear","log"):
            for name in ("prior","posterior"):
                np.testing.assert_allclose(sum(p[f"{kind}_{name}_mass"] for p in subset),1,atol=2e-15)
    values = {"recovered_injection_sigma":shift, "analytic_flat_q95":exact,
              "uncompressed_benchmark_snr":sqrt(rho2), "CBC_quadrature_log_ratio":delta,
              "twice_grid_lisa_snr":refined}
    print(json.dumps(values,indent=2))
    (ROOT/"results").mkdir(exist_ok=True)
    (ROOT/"results/validation.json").write_text(json.dumps(values,indent=2)+"\n")


if __name__ == "__main__":
    main()
