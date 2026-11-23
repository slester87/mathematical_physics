# Multimessenger limits on dark glueball emission

Can three observations of a merger constrain the lightest scalar glueball of a hidden Yang–Mills sector? This study implements one test using a GW distance distribution, spectroscopy of the proposed host, and photon counts from a gamma-ray spectrometer. The output is a table indexed by gauge group, physical confinement scale and escaping photon yield. The bundled event, instrument and benchmark yields are synthetic. The three continuum lattice mass ratios are published results.

## Run

Tested with Python 3.14.3 and NumPy 2.4.3. From this directory run

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python analyze.py example/event.json > /tmp/glueball-limits.csv
.venv/bin/python -m unittest -v
```

[The event manifest](example/event.json) specifies the entire example. [The reference output](example/results.csv) contains all nine points. The two photons in the fixed time and energy window are detector counts of unknown origin. One count is expected from background. The window and synthetic counts were chosen to exercise the calculation.

## From lattice masses to counts

In natural units the lattice computation supplies a dimensionless scalar mass ratio $r_N=m_{0^{++}}/\sqrt{\sigma}$. Table 34 gives $3.781(23)$, $3.405(21)$ and $3.271(27)$ for $SU(2)$, $SU(3)$ and $SU(4)$. We transcribed these three central values and standard errors into [lattice.csv](lattice.csv). The absolute scale $q=\sqrt{\sigma}$ is a free input in MeV. [Athenodorou and Teper, JHEP 12 (2021) 082, Table 34](https://doi.org/10.1007/JHEP12%282021%29082)

The benchmark assumes the merger produces a population of scalar glueballs, with a portal allowing two-photon decay. Photons escape isotropically within the analysis time window. $Y$ counts escaping **photons** integrated over that window. It absorbs production, branching fraction, opacity and time acceptance. Prompt emission, negligible boosts, negligible local gravitational shifts and a negligible intrinsic linewidth are explicit hypotheses. Pure Yang–Mills alone supplies neither the merger yield nor this portal. [Juknevich, Melnikov and Strassler, hidden-sector decays](https://doi.org/10.1088/1126-6708/2009/07/055)

For luminosity distance $D_L$ in cm, host redshift $z$, known mean background $b$, and effective collecting area $A_W(E)$ into the fixed reconstructed-energy window $W$, the model is

$$
E=\frac{r_N q}{2(1+z)},\qquad
\mu=b+\frac{Y(1+z)^2}{4\pi D_L^2} A_W(E),\qquad
K\sim\operatorname{Poisson}(\mu).
$$

The geometric factor converts an integrated emitted photon number to received number per area. $D_L/(1+z)$ is transverse comoving distance. The example assumes a transparent line of sight. [Hogg, distance measures in cosmology](https://arxiv.org/abs/astro-ph/9905116)

## Inputs and detector response

| Input | Meaning and convention |
|---|---|
| GW sample CSV | One row per joint $(D_L,z)$ draw or quadrature node with nonnegative posterior mass. Supply probability mass per node, including prior and integration weights. The upstream analysis conditions on GW data only. Retain distance–redshift correlations from the adopted cosmology and peculiar-velocity model. The example explicitly supplies a synthetic joint distribution on nine nodes. |
| JWST spectrum summary | One identified host line with vacuum rest wavelength, observed centroid and Gaussian centroid uncertainty in micrometres. The code updates each GW node by the wavelength likelihood and renormalizes. JWST can measure the host at a later epoch. Avoid recycling a distance posterior that already incorporates this spectrum. |
| Gamma-ray event list | Unique photon IDs, reconstructed energy in MeV and arrival times in seconds relative to the manifest's merger epoch, converted upstream to the same time reference. Both bounds are lower-inclusive and upper-exclusive. Analysis assumes a fixed sky direction, continuous live coverage and a known background expectation for that window. An empty list with valid headers and full coverage represents zero counts. |
| Detector response | The synthetic sensor has constant effective area within a true-energy band and Gaussian energy redistribution. To use a calibrated response, set `sensor.window_area_csv` to a table with columns `true_energy_MeV,window_low_MeV,window_high_MeV,area_cm2`. Supply the effective area already folded into the chosen reconstructed-energy window and evaluated at this source position and exposure. The code interpolates linearly between nodes and assigns zero outside the tabulated support. The tabulated response supersedes the Gaussian response. |
| Provenance and association | Each CSV observation uses the manifest's event ID. The association field records why the host and observing direction belong to the merger. For measured observations, record the original product IDs, versions, checksums, time system, sky association, source selection and background estimation in the manifest. The analysis conditions on a correct association. It does not discover counterparts or estimate association probabilities. |

The instrument inputs are reduced products. To use flight data, obtain validated strain parameter-estimation samples, extract a calibrated spectral-line centroid, and use the sensor's good-time intervals, background and response for the target. If background uncertainty, a conventional transient component, absorption or source motion is material, include it in the forward model before interpreting a limit. Multiple channels derived from the same photons must retain their statistical dependence.

## What the reported limit means

For fixed $(N,q,Y)$ the code averages the Poisson lower tail over the joint source distribution updated by JWST and over the lattice mass uncertainty. The lattice standard error is modeled as Gaussian and integrated with Gauss–Hermite quadrature. This is a **conditional predictive test** for too few photons under that specified nuisance distribution. The CSV flags a point when $P(K\le k_{\rm obs}\mid d_{\rm GW},d_{\rm host},N,q,Y)\le\alpha$. This probability describes counts under a benchmark. It is not the posterior probability of its gauge group. Repeated-event coverage conditional on every possible fixed nuisance parameter would require a separate construction.

Inverting that tail gives the largest compatible yield at the threshold (the boundary is the reported upper limit). The demo scans up to $10^{54}$ photons. A blank upper limit with `above_scan_max` means that even the maximum yield remained compatible. A background-only lower tail below threshold gives `background_tension` and no signal limit. The test addresses a deficit against a predicted yield. It does not search for positive evidence of a line. The analysis window is fixed across all nine points. Searching multiple windows or reporting a discovery needs its own statistical calibration.

At $q=1$ MeV and $Y=1.2\times10^{52}$ photons the synthetic count is incompatible with the $SU(3)$ benchmark at the 5% threshold. Its yield limit is $8.42\times10^{51}$ photons. The $SU(2)$ and $SU(4)$ points at the same scale survive. The same $SU(3)$ benchmark yield survives at $q=1.1$ MeV. The 48- and 96-node calculations agree on all nine verdicts and on every in-range yield limit to within two parts per million. Tests also check the analytic zero-count limit, mixture calibration, time/energy boundaries, zero response, event IDs, and inverse-square scaling.

## Physical identifiability

An arbitrary change of $q$ can make different groups predict the same line energy because only $r_N q$ enters its central value. A weak portal or negligible production can put every model below detector sensitivity. A second securely identified line could give a scale-independent mass ratio, or an independent scale and a production calculation could allow a stronger exclusion. These data would constrain continuum observables. Comparing Wilson and improved lattice actions that converge to the same theory is a numerical continuum-extrapolation question.

For an observational precedent, Diamond et al. used real GW170817 data to bound radiatively decaying axions. Their production and transport calculation is specific to axions. A merger calculation of the glueball population, velocity distribution, escape probability and time profile would be needed to replace our freely specified photon yield by a prediction for a particular dark sector. [Diamond et al., Phys. Rev. Lett. 132 (2024) 101004](https://doi.org/10.1103/PhysRevLett.132.101004)
