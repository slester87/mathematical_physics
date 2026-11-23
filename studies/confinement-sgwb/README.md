# Can detector data distinguish hidden-confinement spectra?

The O1–O4a stochastic-background data leave the relative probabilities of all 90 retained three-flavor model points essentially unchanged. The strongest of these spectra has expected signal-to-noise ratio (SNR) of 5.96 × 10⁻⁸ even in the ideal four-year LISA forecast. These conclusions apply to two finite microscopic grids with matter, fixed wall and source prescriptions, and the archived transition solutions. [Study figure](reference/reach.svg) · [All 90 points](reference/points.csv) · [Prior art](LITERATURE.md)

## 1. Reproduce detector limits and exercise the strain pipeline

Combine the six LVK O1, O2, O3-HL/HV/LV and O4a-HL cross-correlation spectra using their released masks, errors and 1/32 Hz grid. Inverse-variance weighting gives 50,406 distinct frequencies from 273,711 retained baseline-frequency observations. At each frequency the model in LVK units is Ω = (h²Ω)/0.679². For spectrum s the independent-bin Gaussian log likelihood relative to noise is Σᵢ(Cᵢsᵢ − sᵢ²/2)/σᵢ². These fixed-calibration calculations approximate the collaboration's analysis. [LVK paper, Table 3](https://arxiv.org/abs/2508.20721) · [Data release G2502630-v1](https://dcc.ligo.org/LIGO-G2502630/public)

Power-law amplitude at 25 Hz, upper 95% posterior quantile, in units of 10⁻⁹. Both amplitude priors have endpoints 10⁻¹³ and 10⁻⁶.

| Spectral slope | Uniform | Published | Log-uniform | Published |
|---|---:|---:|---:|---:|
| 0 | 8.44 | 8.6 | 2.78 | 2.8 |
| 2/3 | 6.19 | 6.3 | 2.01 | 2.0 |
| 3 | 0.932 | 1.0 | 0.322 | 0.32 |

A separate strain calculation uses the 32 s, 4096 Hz H1 and L1 GW150914 records. It selects the first 14 s, checks DATA and CBC_CAT1, high-passes at 16 Hz and removes 1 s from each end. The 12 retained seconds span GPS [1126259447, 1126259459). pygwb forms a one-sided real cross spectrum in twelve nonoverlapping Hann segments. The tensor overlap reduction function converts it to Ω. The 30–200 Hz passband and |γ| > 0.1 cut leave 36 bins spanning 30–89 Hz. Their median empirical standard error on Ω is 4.13 × 10⁻⁴. This off-source interval exercises data access, units, detector geometry and normalization. An independent SciPy Welch implementation agrees in relative L² norm to 0.043%. Observing-run limits above use the published long-integration spectra. [GWOSC release](https://gwosc.org/GW150914data/) · [pygwb](https://pygwb.docs.ligo.org/pygwb/)

## 2. Measure sensitivity to the microscopic prior

Each six-by-six-by-six-by-six grid indexes (mσ², mη′², mX², fπ). The first three coordinates are in GeV² and the last is in GeV. The historical SU(3) scan uses three flavors and ξ = 2, and the SU(4) scan uses three flavors and ξ = 5. Each has 1,296 input points. Respectively, 407 and 405 have finite positive transition quantities and physical LTE wall speed and efficiency. Requiring the archived perturbative fraction to reach 90% retains 27 and 63. The archive labels the temperature column Tn, and the forward routine populates it with the percolation temperature. Other vacuum criteria and elastic unitarity were not independently evaluated. The two scans change ξ as well as color number. [Source models](https://doi.org/10.1007/JHEP08%282026%29059) · [Upstream code](https://github.com/miarobin/Eta-Prime-GWs)

Assign to each grid node its midpoint-bounded rectangular cell, clipped to the scan endpoints. Integrate either a product-uniform or product-log-uniform density over those cells and condition on the retained subset. A support test further conditions on the lowest three mη′² nodes. The likelihood includes an additive compact-binary background ∝ f^(2/3) and integrates its 25 Hz amplitude against a log-uniform prior on [10⁻¹³, 10⁻⁶]. Peak spectra use the sound and turbulence shapes in equations 4.10–4.17 and the historical notebook's finite acoustic lifetime. Both priors are choices on the listed microscopic coordinates and grid, with ξ and flavor count fixed.

| Gauge group | Product prior | Full-grid peak Q₉₅ | Lower-mη′² peak Q₉₅ |
|---|---|---:|---:|
| SU(3) | Uniform | 1.41 × 10⁻¹⁷ | 1.84 × 10⁻¹⁷ |
| SU(3) | Log-uniform | 1.41 × 10⁻¹⁷ | 1.41 × 10⁻¹⁷ |
| SU(4) | Uniform | 1.76 × 10⁻¹⁸ | 3.27 × 10⁻¹⁸ |
| SU(4) | Log-uniform | 2.04 × 10⁻¹⁸ | 3.27 × 10⁻¹⁸ |

Every table entry is the same before and after conditioning on LVK. The spread in marginalized log likelihood across either full grid is at most 1.46 × 10⁻¹³. The total variation distance between any prior and its own posterior is below 1.3 × 10⁻¹⁴. Values this small quantify the essentially flat likelihood under the adopted model. They do not express experimental precision. [Machine-readable results](reference/inference.json)

## 3. Compare integrated observational reach

| Spectrum | NANOGrav 15 yr | LISA, ideal 4 yr | LVK O1–O4a |
|---|---:|---:|---:|
| Six-flavor Figure 7 benchmark SNR | 1.95 × 10⁻³¹ | 1.37 × 10⁻¹¹ | 1.50 × 10⁻¹³ |
| Maximum SNR over 90 three-flavor points | 2.26 × 10⁻²⁸ | 5.96 × 10⁻⁸ | 5.49 × 10⁻¹³ |

The three-flavor peaks span 0.049–7.47 Hz. The point with the largest SNR in each experiment peaks at 0.235 Hz with h²Ω = 3.38 × 10⁻¹⁷.

LVK uses ρ² = Σᵢ(sᵢ/σᵢ)². NANOGrav uses its tabulated full-array effective noise including common-process power, ρ² = 2T ∫ (Ω/Ωeff)² df, T = 15 yr, f ≥ 1/T, and h = 0.674 for the published Ω column. The LISA A,E instrument forecast uses the Smith–Caldwell effective noise, ρ² = T ∫ (Ω/ΣΩ)² df, T = 4 yr, integrated from 0.1 mHz to 0.1 Hz. It yields h²Ω = 2.15 × 10⁻¹³ at SNR 5 for a flat spectrum (published approximation 2.1 × 10⁻¹³). The PTA calculation forecasts sensitivity using measured noise. A pulsar timing likelihood and LISA foreground or instrumental-noise marginalization are outside this study. [NANOGrav sensitivity data](https://doi.org/10.5281/zenodo.8092346) · [Smith & Caldwell](https://arxiv.org/abs/1908.00546)

The separate six-flavor control is the solid purple curve at lower right in Houtz, Ulloa & West Figure 7, SU(3), F = 6, ξ = 1. The inferred microscopic coordinates are mσ² = mX² = 10⁶ GeV², mη′² = 5156.620156 GeV² and fπ = 1500√3 GeV. The authors provide no unique row identifier for that curve. For fixed transition inputs in benchmark.json, our grid peak is 1.135 Hz at h²Ω = 8.29 × 10⁻¹⁹. The digitized journal peak is approximately 1.139 Hz at 7.88 × 10⁻¹⁹. The largest difference across the 62 vector vertices is 6.66%. Digitized Figure 7 data are adapted from Rachel Houtz, Martha Ulloa and Mia West under CC BY 4.0. [Article](https://doi.org/10.1007/JHEP08%282026%29059) · [License](https://creativecommons.org/licenses/by/4.0/) · [Extracted coordinates](data/figure7.csv)

A microscopic cross-check solves one three-flavor SU(3) point afresh with the pinned upstream effective-potential and wall solver on a 150 × 150 dressed-mass mesh. At mσ² = mη′² = mX² = 10⁶ GeV² and fπ = 1102.27038425243 GeV, T changes by 0.0065 GeV, α rises by 10.96% and β/H rises by 0.21%. Starting from the archived peak of 5.88 × 10⁻²¹, the macOS and Linux reruns give 6.78 and 6.72 × 10⁻²¹, increases of 15.3% and 14.3%. Another Linux run entered the wall routine's nonconvergence path and failed while evaluating the efficiency. The wrapper skips efficiency at the upstream zero-speed sentinel and records an unresolved LTE peak as null. A replay with the guard recovered T = 781.209 GeV and β/H = 12302.63, while the wall solver returned its zero-speed sentinel. The spectrum was recorded as undetermined. [Guarded solver output](reference/microcheck-unresolved.json) · [Workflow](https://github.com/slester87/mathematical_physics/actions/runs/45093774760) [Original failed replay](https://github.com/slester87/mathematical_physics/actions/runs/45093132196)

This is a one-point check using the same solver family. Systematic grid refinement, a second physical solver and checks of scan cells between accepted nodes remain open. [macOS calculation](reference/microcheck.json) · [Linux calculation](reference/microcheck-linux.json) · [Independent workflow run](https://github.com/slester87/mathematical_physics/actions/runs/45092749855)

## Run from a fresh checkout

The following commands use separate environments for the detector and microscopic calculations. Input downloads are cached in this study and checked against the recorded digests. Rebuilt tables appear in results/. Reference outputs above are reviewable snapshots.

```sh
cd studies/confinement-sgwb
python3.11 -m venv .venv
.venv/bin/pip install numpy==1.26.4
.venv/bin/python study.py
.venv/bin/python validate.py
.venv/bin/pip install -r strain-requirements.txt
.venv/bin/python strain.py
.venv/bin/pip install reportlab==4.4.9
.venv/bin/python figure.py
```

```sh
python3.12 -m venv .micro
.micro/bin/pip install numpy==2.3.5 scipy==1.15.3 cosmoTransitions==2.0.7
git clone https://github.com/miarobin/Eta-Prime-GWs /tmp/confinement-eta-prime
.micro/bin/python microcheck.py /tmp/confinement-eta-prime
```

The microscopic script reads the pinned revision with git show, removes unused plotting imports and updates the deprecated NumPy int alias in a temporary directory. The historical scan blobs and all external input hashes are recorded alongside the download code. Continuous integration downloads the original inputs, runs both data paths and the microscopic calculation, and exports the strain environment. The recorded Linux CPython 3.11.18 environment can also be installed with pip install -r reference/strain-linux-py311.txt. Validation checks the analytic truncated-normal limit, a five-sigma injection, the uncompressed baseline likelihood, independent foreground quadrature, the digitized spectrum and LISA integration refinement. [Input versions](inputs.py) · [Checksums](data/sha256.txt) · [Checks](validate.py) · [Workflow](../../.github/workflows/confinement-sgwb.yml)
