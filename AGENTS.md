# Oasis Lab Site Agent Context

This repository is the Oasis Lab static website. Treat publication changes as a gated workflow, not as a plain CSV edit.

## Publication Change Workflow

When adding or editing publications:

1. Update `static/publications.csv` using the existing column order.
2. Prefer local paper PDFs in `static/papers/`, referenced as `../static/papers/<file>.pdf`.
3. Keep DOI or publisher pages in `url_page`; do not use publisher PDF links as the main PDF when a local hosted PDF is available.
4. If adding a PDF, scan it for repository and dataset candidates:

   ```sh
   ./venv/bin/python scripts/manage_publication_pdfs.py --extract-links
   ```

5. Fill `url_code` and `url_dataset` whenever the PDF or official page exposes a project, artifact, code, or dataset link.
6. Check all publication links:

   ```sh
   ./venv/bin/python scripts/manage_publication_pdfs.py --check-links
   ```

7. Build the site:

   ```sh
   ./venv/bin/python freeze.py
   ```

## Commit Gate

This repo uses `.githooks/pre-commit`. It runs automatically for commits that touch `static/publications.csv` or `static/papers/` when local Git has:

```sh
git config core.hooksPath .githooks
```

The gate checks:

- existing local paper PDFs are present;
- remote paper PDFs are not used where local hosting is expected;
- orphan PDFs are not left in `static/papers/`;
- newly staged PDFs do not contain unrecorded code/dataset candidates;
- all publication links are reachable.

Future accepted papers without PDFs are reported but do not block commits.
