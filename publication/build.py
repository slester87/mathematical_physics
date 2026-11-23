"""Build the research notebook with Python 3.11+ and the standard library."""
from datetime import date
from html import escape
from pathlib import Path
from shutil import copyfile
from string import Template
import runpy
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "publication"
REPO = "https://github.com/slester87/mathematical_physics"


def page(title, description, home, body):
    return Template((HERE / "page.html").read_text()).substitute(
        title=escape(title), description=escape(description, quote=True),
        home=home, repo=REPO, body=body,
    )


def render_study(manifest, output):
    folder = manifest.parent
    study = folder.parent
    slug = study.name
    meta = tomllib.loads(manifest.read_text())
    published = meta["date"]
    if not isinstance(published, date):
        raise ValueError(f"{manifest}: date must be a TOML date")
    title, kind, summary = (escape(meta[k]) for k in ("title", "kind", "summary"))
    date_html = f'<time datetime="{published.isoformat()}">{published.day} {published:%B %Y}</time>'
    source = f"{REPO}/tree/main/studies/{slug}"
    target = output / "studies" / slug
    target.mkdir(parents=True, exist_ok=True)
    parts = {}
    if (folder / "figures.py").exists():
        parts = runpy.run_path(str(folder / "figures.py"))["render"](study)
    for name, relative_path in meta.get("downloads", {}).items():
        if Path(name).name != name:
            raise ValueError(f"Download name must be a filename: {name}")
        copyfile(study / relative_path, target / name)
    article = Template((folder / "article.html").read_text()).substitute(source=source, **parts)
    body = f"""<article><header class="article-head"><a class="back" href="../../#studies">← Study index</a>
    <p class="meta"><span>{kind}</span> <i>/</i> {date_html}</p>
    <h1>{title}</h1><p class="dek">{summary}</p></header>
    {article}</article>"""
    (target / "index.html").write_text(page(meta["title"] + " · Mathematical physics", meta["summary"], "../../", body))
    href = f"studies/{slug}/"
    cover = parts.get("cover", "")
    entry = f"""<article class="entry{' with-figure' if cover else ''}"><div class="entry-copy">
    <p class="meta"><span>{kind}</span> <i>/</i> {date_html}</p>
    <h3><a href="{href}">{title}</a></h3><p class="summary">{summary}</p>
    <a class="read" href="{href}">Read study <span aria-hidden="true">→</span></a></div>{cover}</article>"""
    return published, slug, entry


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    copyfile(HERE / "style.css", output / "style.css")
    entries = sorted((render_study(m, output) for m in ROOT.glob("studies/*/publication/study.toml")), reverse=True)
    count = len(entries)
    body = f"""<header class="intro"><h1>Mathematical physics<span class="endmark">.</span></h1>
    <p>Studies in gauge theory, dark matter, and their observable signatures.</p></header>
    <section id="studies" aria-labelledby="index-title"><div class="section-rule">
    <h2 id="index-title">Study index</h2><span>{count} published {'study' if count == 1 else 'studies'}</span></div>
    {''.join(entry for _, _, entry in entries)}</section>"""
    (output / "index.html").write_text(page("Mathematical physics · Research notebook", "Computational studies in mathematical physics with figures, source data, and reproducible calculations.", "./", body))


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "_site")
