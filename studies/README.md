# Studies

[Multimessenger limits on dark glueball emission](multimessenger-yang-mills/README.md)

## Planned spectrum reproduction

**Planned:** Reproduce one published gravitational-wave spectrum from the [Houtz–Ulloa–West research code](https://github.com/miarobin/Eta-Prime-GWs). The first milestone is to identify the exact figure, curve, and parameter point and pin the upstream revision. Compare the peak frequency, peak amplitude, and shape of the spectrum. Repeat with finer numerical settings before varying physical parameters, so that numerical error and parameter sensitivity can be estimated separately.

## Starting a study

Keep each investigation in `studies/<short-name>/`. Its README should give the question, the paper or dataset, and the command or notebook evaluation that reproduces the result. Record input versions, parameter values, units, and the environment alongside the calculation.

Use Python for numerical work and Wolfram Language (Mathematica) for symbolic work where appropriate. For a published figure, retain the numerical values behind the plot and describe how the reference values were obtained.
