# Astronomical event evidence catalog

Given an astronomical event, which instruments observed it, which observations corroborate one another, and which inputs does a specified theory still need? The catalog answers those questions with a local SQLite database, source-specific searches, and reviewed evidence. It runs with Python 3.11+ using the standard library. It stores metadata and compact measurements. Large detector files stay at their archives.

## Run the worked events

From the repository root:

```sh
python3 -m event_catalog sync event_catalog/examples/GW170817.json --only reviewed
python3 -m event_catalog sync event_catalog/examples/SN1987A.json --only reviewed
python3 -m event_catalog report AT2017gfo --theory event_catalog/theories/prompt-glueball.json
python3 -m event_catalog report SN1987A --format json
```

The reviewed fixtures run offline. GW170817 includes 16 sourced records across gravitational waves, gamma rays, X-rays, ultraviolet, optical, radio and neutrinos. Fermi/GBM and INTEGRAL/SPI-ACS corroborate the prompt burst. Swope and DECam corroborate the optical transient. The Fermi-LAT entry at coalescence records a coverage gap, while its later measurement bounds the 100–1000 MeV energy flux over 1153–2027 s. The host redshift is present. Five additional reduced inputs remain outstanding for the included prompt-line theory checklist. SN1987A demonstrates two distinct neutrino instruments reporting the same burst with different event counts and selection functions. The program does not sum those counts.

## Register a new event

```sh
python3 -m event_catalog new EXAMPLE-TRANSIENT --alias EXAMPLE-ALERT \
  --utc 2030-01-12T04:05:00Z --cone 12.5 -26.1 0.1 --days -3 90 > event.json
python3 -m event_catalog sync event.json
python3 -m event_catalog report EXAMPLE-ALERT --format json
```

The example command uses invented coordinates and time. Set `origin` to `synthetic` when simulating. Record the epoch, localization source, reference frame and scope of the search in the manifest. Add independently established event and counterpart aliases. Keep a host designation in `host` to avoid matching every paper about that galaxy. Any number of ICRS search cones may be supplied. For a sky map, record its URL and version, and provide covering cones for the credible region of interest. The spatial adapters require cones and an epoch. Other sources can be queried while localization is pending. The default window is one day before through thirty days after the epoch. Widen it for older host data and late afterglows.

`--gwosc` accepts a versioned GWOSC name, `--gracedb` a public superevent ID, and `--gbm` a GBM trigger ID. Each is optional. An event may change from provisional to confirmed or retracted. Re-run sync on the revised manifest to update its dossier. Search windows, instrument choices and new theory definitions can evolve independently. Collection is on demand.

## Discover and extend sources

| Source | Retrieval and interpretation |
|---|---|
| GWOSC and GraceDB | Versioned strain, parameter and timeline collection links, plus public superevent information when its identifier is known. An archive listing of instruments is not an individual detection. [GWOSC API](https://gwosc.org/api/) · [GraceDB](https://gracedb.ligo.org/) |
| Fermi/GBM | Paginated public NASA archive listing for an associated trigger, including time-tagged data, count spectra and response files by detector. A file locator does not establish exposure to the source. [NASA archive](https://registry.opendata.aws/nasa-heasarc/) |
| NASA GCN | Search the daily JSON archive by event labels, subjects and mentions in the body, recording which field matched. Bulletins remain candidates, including retractions and circulars citing earlier events. A local archive can be selected with `sources.gcn.path`. [Circular archive](https://gcn.nasa.gov/docs/circulars/archive) |
| MAST and ESO | Search MAST’s CAOM cone service, filter observations by time, and query ESO’s ObsCore service for observation footprints intersecting the sky region and time window. Both paginate and flag a truncated search. Candidate observations can come from HST, JWST and ESO facilities. [MAST](https://mast.stsci.edu/api/v0/) · [ESO](https://archive.eso.org/tap_obs/examples) |
| Crossref | Find DOI records using event and counterpart aliases. Keep titles with an exact designation match and label bounded or truncated searches. Papers that omit the event name from their titles can be added during review. [Crossref API](https://api.crossref.org/) |
| arXiv | Search event and counterpart aliases in preprints, verify the designation in the title or abstract, and retain the article version and DOI where available. Searches record when the result cap was reached. [arXiv API](https://info.arxiv.org/help/api/user-manual.html) |
| Reviewed evidence and CSV tables | Any facility or messenger can contribute typed measurements, limits, coverage statements or checksummed files. Include the original citation and underlying dataset lineage. |

Discover additional TAP services advertising ObsCore and use the resulting registry file:

```sh
python3 -m event_catalog discover-archives > archives.json
python3 -m event_catalog sync event.json --archives archives.json
```

Registry discovery lists advertised compatible services. Some observatories have separate APIs or proprietary data. Inspect the registry before a large run. Use `--only mast eso` or another subset as needed. The catalog records which configured sources were unqueried, missing inputs, empty, partial, failed or returned records. TAP services with incompatible formats, missing time/footprint metadata, publication lag and field-of-view restrictions all affect how much can be found. `empty` describes the archive query; an instrumental nondetection needs a source that reports it.

To add a sensor from a published CSV, put a source entry like the following under `sources`. Replace placeholders with the publisher's names and event-specific definitions. Use `url` for a remote table or `path` relative to the manifest for a local one. The adapter retains the original columns and hashes the source bytes.

```json
{
  "radio-table": {
    "adapter":"measurement_csv", "path":"published.csv",
    "select":{"event":"EXAMPLE-TRANSIENT"},
    "columns":{"key":"row_id","value":"flux_uJy","sigma":"error_uJy"},
    "defaults":{"sensor":"instrument name","channel":"radio","subject":"counterpart",
      "kind":"measurement","resource":"flux_density","unit":"uJy","level":"summary",
      "reference":"https://example.org/published-table","description":"Published flux density",
      "association":"candidate","lineage":["publisher/dataset-id"]}
  }
}
```

For mixed detections and limits, map the appropriate `kind` per row or import filtered subsets. Define the band, epoch and convention before comparing measurements. `single_event: true` is allowed for a verified single-event table. Additional native APIs can be implemented by registering one function in `archives.ADAPTERS` and supplying its configuration in the manifest.

## Provenance and theory checks

Use `--db PATH` before the command to select a database. `history EVENT` lists every search attempt. `snapshot SHA256` retrieves its normalized evidence. Repeated identical batches share storage. A failed refresh preserves the preceding batch for the same search scope and marks it stale. Theory checks exclude stale records. A change in sky region, time window, identifiers or status creates a new scope. Previous batches remain accessible through history.

Each report links evidence to the source, sensor, messenger, subject and known upstream datasets. Corroboration requires two confirmed detections of the same declared phenomenon from different sensors with disjoint, recorded lineages. This supports source review; unrecorded shared calibration or systematics remain possible. For quantitative comparisons opt in with a common `comparison_key` and `uncertainty: gaussian_1sigma` only when the measurand, band, time, frame, and independence assumptions agree. The report returns the difference divided by the quadrature sum of the uncertainties.

Define another theory by copying [the prompt-line input contract](theories/prompt-glueball.json). Match any stated resource, messenger, measurement type or unit. Require time and energy coverage and a common sensor for jointly calibrated inputs. Time intervals are seconds relative to the manifest epoch; energies are observer-frame MeV. For reduced inputs use `level: checked_file`, a manifest-relative `file` and a `sha256`. The reviewed importer verifies the bytes. The curator establishes that the contents, calibration, units and association are scientifically valid. A provisional association, published paper, or sky/time overlap by itself cannot qualify as a validated detector file.

`inputs_complete` reports availability under the specified contract. A physical verdict requires a separate forward model and likelihood. The [existing Yang–Mills study](../studies/multimessenger-yang-mills/README.md) illustrates that step. Its bundled event is synthetic. The evidence catalog keeps measured and simulated events explicitly labeled.

```sh
python3 -m unittest -v event_catalog.test_catalog
```
