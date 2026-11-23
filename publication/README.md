# Publishing a study

Add `publication/study.toml` and `publication/article.html` inside the study directory. The manifest supplies `title`, `kind`, a TOML `date`, and `summary`. Optional `[downloads]` entries map public filenames to study-relative source files. An optional `publication/figures.py` can define `render(study_directory)` and return named HTML fragments for the article template, including a `cover` figure for the index. The [multimessenger study](../studies/multimessenger-yang-mills/publication/) provides a working example.

Run `python3 publication/build.py` with Python 3.11 or later, then `python3 -m http.server --directory _site` to preview. GitHub Actions rebuilds the index in reverse publication order and deploys the studies to Pages on pushes to `main`.
