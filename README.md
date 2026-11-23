# Mathematical physics

Computational and analytical studies of gauge theory, dark matter, and possible observational signatures. We start with published results that we can independently reproduce, then investigate a specific uncertainty or extension.

[Read the research notebook on GitHub Pages](https://slester87.github.io/mathematical_physics/)

## Planned spectrum reproduction

**Planned:** Reproduce one published gravitational-wave spectrum from the [Houtz–Ulloa–West research code](https://github.com/miarobin/Eta-Prime-GWs). The first milestone is to identify the exact figure, curve, and parameter point and pin the upstream revision. Compare the peak frequency, peak amplitude, and shape of the spectrum. Repeat with finer numerical settings before varying physical parameters, so that numerical error and parameter sensitivity can be estimated separately.

## Multimessenger Yang–Mills study

[Joint event analysis](studies/multimessenger-yang-mills/) combines a gravitational-wave distance distribution, host spectroscopy and gamma-ray counts to test specified dark glueball emission models. The runnable example uses a synthetic event and published continuum lattice masses.

## Starting a study

Keep each investigation in `studies/<short-name>/`. Its README should give the question, the paper or dataset, and the command or notebook evaluation that reproduces the result. Record input versions, parameter values, units, and the environment alongside the calculation.

Use Python for numerical work and Wolfram Language (Mathematica) for symbolic work where appropriate. For a published figure, retain the numerical values behind the plot and describe how the reference values were obtained.

## Publishing a study

Add `publication/study.toml` and `publication/article.html` inside the study directory. The manifest supplies `title`, `kind`, a TOML `date`, and `summary`. Optional `[downloads]` entries map public filenames to study-relative source files. An optional `publication/figures.py` can define `render(study_directory)` and return named HTML fragments for the article template, including a `cover` figure for the index. The first study provides a working example.

Run `python3 publication/build.py` with Python 3.11 or later, then `python3 -m http.server --directory _site` to preview. GitHub Actions rebuilds the index in reverse publication order and deploys the studies to Pages on pushes to `main`.
