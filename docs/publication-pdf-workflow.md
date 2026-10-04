# Publication PDF Workflow

Use this workflow when adding or refreshing paper PDFs for the static website.

## Audit

Run a read-only scan:

```sh
./venv/bin/python scripts/manage_publication_pdfs.py
```

Scan local PDFs for code and dataset candidates:

```sh
./venv/bin/python scripts/manage_publication_pdfs.py --extract-links
```

Check every publication link:

```sh
./venv/bin/python scripts/manage_publication_pdfs.py --check-links
```

The report groups papers into:

- `Local PDF path missing`: CSV points to `../static/papers/*.pdf`, but the file is absent.
- `Remote paper PDF`: CSV still points to a direct remote paper PDF.
- `Needs logged-in browser`: ACM/IEEE-style page that needs a signed-in Chrome session.
- `No PDF known yet`: no PDF URL or known publisher download page.
- `Orphan local PDF`: file exists in `static/papers/` but is not referenced by CSV.
- `Author list not parseable`: the `authors` column is not a valid Python list of names, so the site would render the paper without authors.

`--validate` is the gate used by the deploy workflow. It exits non-zero only for problems that would break the published site (unparseable author lists, missing local PDFs), so unreleased papers without a PDF do not block deployment.

For CI-style checks:

```sh
./venv/bin/python scripts/manage_publication_pdfs.py --strict
```

## Open PDFs

Once a downloadable camera-ready or public PDF exists, download it by default. For direct public PDF URLs, download and rewrite CSV links locally:

```sh
./venv/bin/python scripts/manage_publication_pdfs.py --download-open --write
```

The script only auto-downloads known open direct-PDF hosts such as USENIX, CUHK, arXiv, and OpenReview.

## ACM / IEEE PDFs

Publisher PDFs that require institutional access should be downloaded from a logged-in Chrome session by default:

1. Sign in to ACM DL / IEEE Xplore / SJTU access in Chrome.
2. Run the audit script and look at `Needs logged-in browser`.
3. Download the PDFs through the publisher page.
4. Copy them into `static/papers/` using the script's suggested file names.
5. Update the `url_pdf` column in `static/publications.csv` to `../static/papers/<file>.pdf`.

If access fails, ask the user to sign in to ACM DL / IEEE Xplore / SJTU access in Chrome and retry. Do not ask for passwords or cookies.

## Metadata Policy

- `url_page`: fill it whenever an official paper, DOI, conference, ACM, IEEE, USENIX, or author page is available. It is not mandatory before one exists.
- `url_pdf`: once a PDF can be downloaded, host it locally in `static/papers/`.
- `url_code` and `url_dataset`: only fill these from links extracted from the paper PDF. Do not use general web search to guess repositories or datasets.
- `url_artifact` (13th and last column, shown as an "Artifact" button): an artifact-evaluation archive linked from the paper, typically a Zenodo record. Same rule as above: only from the PDF. Rows without it may simply stop after `url_page`.
- `url_video` and `url_slides`: check the publication being added or edited and fill them when official pages expose them.
- Link failures: 404 and missing local files must be fixed. 403/timeout caused by anti-bot behavior may pass after browser verification.

## Recent-10 Backfill

Every publication update should also review the 10 most recent publications in `static/publications.csv` for newly available metadata:

- official paper, conference, DOI, ACM, IEEE, USENIX, or author pages for `url_page`;
- downloadable camera-ready or public PDFs that can now be localized in `static/papers/`;
- official videos, talks, and slides for `url_video` and `url_slides`.

This is a targeted backfill pass, not a full historical web search. Do not re-check older publications unless the user asks, a link audit reports a concrete issue, or a paper is already being edited for another reason.

If the recent-10 pass adds a PDF, run the PDF link extraction and only fill `url_code` or `url_dataset` from repository or dataset links found inside that PDF.

Whenever a new PDF is added, run:

```sh
./venv/bin/python scripts/manage_publication_pdfs.py --extract-links
```

If the PDF contains candidate repository or dataset links, make sure `url_code` and `url_dataset` are filled in `static/publications.csv`.

How the scan works, so you know what to trust:

- It reads link annotations and the text inside compressed PDF streams (a plain byte search misses nearly everything in LaTeX PDFs).
- A GitHub/GitLab link is reported as a candidate when its path matches the paper title or artifact wording, or when the paper text says "available at", "we release", "open-sourced" and similar right before it. Third-party tools such as fio or RocksDB are not reported. GitHub paths containing `data` or `traces` are reported as datasets.
- It only lists candidates. Read the sentence around the link in the PDF before filling `url_code`/`url_dataset`: a cited prior dataset or a supplementary-material link is not the paper's own artifact.
- A candidate such as a Zenodo archive can still be listed after the main link is recorded; that is informational.

## Verification

After changes:

```sh
./venv/bin/python -B -c "from data_utils import load_publications; print(len(load_publications()))"
./venv/bin/python scripts/manage_publication_pdfs.py
./venv/bin/python scripts/manage_publication_pdfs.py --extract-links
./venv/bin/python scripts/manage_publication_pdfs.py --check-links
./venv/bin/python freeze.py
```

Expected state before publishing:

- Paper PDFs point to `../static/papers/*.pdf`.
- Remote `.pdf` links in generated pages should be slides only, not paper PDFs.
- `static/papers/` should have no orphan files unless intentionally staged for future use.
- Publication links should have zero validity failures.
