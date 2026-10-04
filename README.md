# Oasis Lab Website

This is the Flask/Frozen-Flask source for the Oasis Lab website.

## Local development

```bash
python -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python app.py
```

## Static build

```bash
./venv/bin/python freeze.py
```

The generated GitHub Pages site is written to `build/`. Besides the three pages it contains `404.html` (served by GitHub Pages for unknown URLs), `robots.txt` and `sitemap.xml`; the last two are built from `SITE_URL`.

The site's public origin (used for canonical and Open Graph URLs) defaults to `https://oasis-sjtu.github.io`; set the `SITE_URL` environment variable to build for a different domain.

## Updating content

- People: edit `data/people.csv` (columns: `group, name, role, workplace, interests, photo, email, website, scholar, github, dblp`). Put photos in `static/figures/`, resized to about 640px on the long side; they are shown at roughly 170x210px. For alumni, write the degree and graduation year in `role`, e.g. `PhD Alumnus, 2025`.
- Research areas: edit `data/research.csv`.
- News: edit `data/news.csv`.
- Publications: edit `static/publications.csv`, following the same format as the personal site. The page sorts entries newest first by the `year` column (`YYYY.M`, so `2026.10` is October 2026), so row order in the CSV does not matter. The `authors` column is a Python list literal; the audit below flags rows that fail to parse. The Publications page has a search box and venue filters; its state is kept in the URL (`?conf=OSDI,FAST&q=slow`), so a filtered view can be shared. Columns, in order: `title, award, authors, year, conference, shortconf, url_pdf, url_code, url_dataset, url_slides, url_video, url_page, url_artifact`; trailing empty columns may be omitted.

Adding or editing publications, PDFs and links follows the workflow in [`AGENTS.md`](AGENTS.md) and [`docs/publication-pdf-workflow.md`](docs/publication-pdf-workflow.md).

## Deployment notes

- GitHub Actions rebuilds and deploys the site on every push to `master` and once a day. The build runs `manage_publication_pdfs.py --validate` first and fails if an author list cannot be parsed or a local PDF is missing. The runner is pinned to `ubuntu-24.04`; bump it deliberately after testing.
- Dataset download counts are scraped from Tianchi by `scripts/update_dataset_metrics.py`. The last good values are kept in the Actions cache; if a scrape fails the workflow shows a warning and the site keeps showing the cached counts.
- Bootstrap comes from the Bootstrap-Flask package and the Roboto/Merriweather web fonts are self-hosted in `static/fonts/` (Fontsource builds, SIL OFL; license files alongside), so pages load no third-party CSS, JS or fonts. The only third-party content is the Apple Music player on the home page.
