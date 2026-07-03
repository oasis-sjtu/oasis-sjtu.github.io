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

The generated GitHub Pages site is written to `build/`.

## Updating content

- People: edit `data/people.csv`. Template rows for PhD, MS, undergraduate, and alumni entries are included in that same file.
- Research areas: edit `data/research.csv`.
- News: edit `data/news.csv`.
- Publications: edit `static/publications.csv`, following the same format as the personal site.
