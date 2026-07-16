# Publication PDF Workflow

Use this workflow when adding or refreshing paper PDFs for the static website.

## Audit

Run a read-only scan:

```sh
./venv/bin/python scripts/manage_publication_pdfs.py
```

The report groups papers into:

- `Local PDF path missing`: CSV points to `../static/papers/*.pdf`, but the file is absent.
- `Remote paper PDF`: CSV still points to a direct remote paper PDF.
- `Needs logged-in browser`: ACM/IEEE-style page that needs a signed-in Chrome session.
- `No PDF known yet`: no PDF URL or known publisher download page.
- `Orphan local PDF`: file exists in `static/papers/` but is not referenced by CSV.

For CI-style checks:

```sh
./venv/bin/python scripts/manage_publication_pdfs.py --strict
```

## Open PDFs

For direct public PDF URLs, download and rewrite CSV links locally:

```sh
./venv/bin/python scripts/manage_publication_pdfs.py --download-open --write
```

The script only auto-downloads known open direct-PDF hosts such as USENIX, CUHK, arXiv, and OpenReview.

## ACM / IEEE PDFs

Publisher PDFs that require institutional access should be downloaded from a logged-in Chrome session:

1. Sign in to ACM DL / IEEE Xplore / SJTU access in Chrome.
2. Run the audit script and look at `Needs logged-in browser`.
3. Download the PDFs through the publisher page.
4. Copy them into `static/papers/` using the script's suggested file names.
5. Update the `url_pdf` column in `static/publications.csv` to `../static/papers/<file>.pdf`.

## Verification

After changes:

```sh
./venv/bin/python -B -c "from data_utils import load_publications; print(len(load_publications()))"
./venv/bin/python scripts/manage_publication_pdfs.py
./venv/bin/python freeze.py
```

Expected state before publishing:

- Paper PDFs point to `../static/papers/*.pdf`.
- Remote `.pdf` links in generated pages should be slides only, not paper PDFs.
- `static/papers/` should have no orphan files unless intentionally staged for future use.
