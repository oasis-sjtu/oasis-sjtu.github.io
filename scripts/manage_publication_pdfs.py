#!/usr/bin/env python3
import argparse
import csv
import json
import re
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
PUBLICATIONS_CSV = ROOT / "static" / "publications.csv"
PAPERS_DIR = ROOT / "static" / "papers"
PDF_PREFIX = "../static/papers/"

FIELDNAMES = [
    "title",
    "award",
    "authors",
    "year",
    "conference",
    "shortconf",
    "url_pdf",
    "url_code",
    "url_dataset",
    "url_slides",
    "url_video",
    "url_page",
]

OPEN_PDF_HOSTS = {
    "www.usenix.org",
    "usenix.org",
    "www.cse.cuhk.edu.hk",
    "cse.cuhk.edu.hk",
    "arxiv.org",
    "openreview.net",
}

STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "for",
    "in",
    "is",
    "of",
    "on",
    "the",
    "to",
    "with",
}


@dataclass
class Publication:
    row_number: int
    row: List[str]

    def get(self, field: str) -> str:
        index = FIELDNAMES.index(field)
        return self.row[index].strip() if index < len(self.row) else ""

    def set(self, field: str, value: str) -> None:
        index = FIELDNAMES.index(field)
        while len(self.row) <= index:
            self.row.append("")
        self.row[index] = value


@dataclass
class AuditItem:
    row: int
    shortconf: str
    title: str
    url_pdf: str
    url_page: str
    suggested_file: Optional[str] = None
    download_url: Optional[str] = None
    reason: Optional[str] = None


def clean_slug(value: str) -> str:
    value = value.lower()
    value = value.replace("'", "")
    tokens = re.findall(r"[a-z0-9]+", value)
    useful = [token for token in tokens if token not in STOPWORDS]
    return "-".join(useful) or "paper"


def conference_slug(shortconf: str, year: str) -> str:
    match = re.search(r"([A-Za-z]+)'?(\d{2})", shortconf or "")
    if match:
        return f"{match.group(1).lower()}{match.group(2)}"
    year_match = re.search(r"20(\d{2})", year or "")
    prefix_match = re.search(r"([A-Za-z]+)", shortconf or "")
    if prefix_match and year_match:
        return f"{prefix_match.group(1).lower()}{year_match.group(1)}"
    return clean_slug(shortconf or "paper")


def suggested_pdf_name(publication: Publication) -> str:
    conf = conference_slug(publication.get("shortconf"), publication.get("year"))
    title_words = clean_slug(publication.get("title")).split("-")
    return f"{conf}-{'-'.join(title_words[:4])}.pdf"


def is_local_pdf(url_pdf: str) -> bool:
    return url_pdf.startswith(PDF_PREFIX)


def local_pdf_path(url_pdf: str) -> Path:
    return ROOT / url_pdf.replace("../", "", 1)


def is_remote_pdf(url_pdf: str) -> bool:
    parsed = urlparse(url_pdf)
    return parsed.scheme in {"http", "https"} and parsed.path.lower().endswith(".pdf")


def is_open_direct_pdf(url_pdf: str) -> bool:
    parsed = urlparse(url_pdf)
    return is_remote_pdf(url_pdf) and parsed.netloc.lower() in OPEN_PDF_HOSTS


def doi_from_url(url: str) -> Optional[str]:
    if not url:
        return None
    match = re.search(r"10\.\d{4,9}/[^\s?#]+", url)
    return match.group(0).rstrip("/")


def acm_pdf_url(publication: Publication) -> Optional[str]:
    for field in ("url_page", "url_pdf"):
        url = publication.get(field)
        if "dl.acm.org/doi" in url or "doi.org/10.1145/" in url:
            doi = doi_from_url(url)
            if doi and doi.startswith("10.1145/"):
                return f"https://dl.acm.org/doi/pdf/{doi}?download=true"
    return None


def ieee_pdf_url(publication: Publication) -> Optional[str]:
    page = publication.get("url_page")
    if "ieeexplore.ieee.org" not in page:
        return None
    article_match = re.search(r"arnumber=(\d+)", page)
    if not article_match:
        article_match = re.search(r"/document/(\d+)", page)
    if not article_match:
        return "https://ieeexplore.ieee.org/"
    return f"https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber={article_match.group(1)}"


def read_publications(path: Path) -> List[Publication]:
    with path.open(newline="", encoding="utf-8") as csvfile:
        return [Publication(index, row) for index, row in enumerate(csv.reader(csvfile), 1)]


def write_publications(path: Path, publications: Iterable[Publication]) -> None:
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile, lineterminator="\n")
        writer.writerows(publication.row for publication in publications)


def referenced_local_paths(publications: Iterable[Publication]) -> Dict[Path, Publication]:
    referenced: Dict[Path, Publication] = {}
    for publication in publications:
        url_pdf = publication.get("url_pdf")
        if is_local_pdf(url_pdf):
            referenced[local_pdf_path(url_pdf)] = publication
    return referenced


def audit(publications: List[Publication]) -> Dict[str, List[AuditItem]]:
    local_missing: List[AuditItem] = []
    remote_pdf: List[AuditItem] = []
    missing_pdf: List[AuditItem] = []
    browser_required: List[AuditItem] = []

    for publication in publications:
        url_pdf = publication.get("url_pdf")
        title = publication.get("title")
        item = AuditItem(
            row=publication.row_number,
            shortconf=publication.get("shortconf"),
            title=title,
            url_pdf=url_pdf,
            url_page=publication.get("url_page"),
            suggested_file=suggested_pdf_name(publication),
        )

        if is_local_pdf(url_pdf):
            if not local_pdf_path(url_pdf).exists():
                item.reason = "local PDF path does not exist"
                local_missing.append(item)
            continue

        if is_remote_pdf(url_pdf):
            item.download_url = url_pdf
            item.reason = "remote direct PDF"
            remote_pdf.append(item)
            continue

        if not url_pdf:
            acm_url = acm_pdf_url(publication)
            ieee_url = ieee_pdf_url(publication)
            if acm_url or ieee_url:
                item.download_url = acm_url or ieee_url
                item.reason = "requires logged-in browser download"
                browser_required.append(item)
            else:
                item.reason = "no PDF URL"
                missing_pdf.append(item)

    referenced = referenced_local_paths(publications)
    orphan_pdf = [
        AuditItem(
            row=0,
            shortconf="",
            title=path.name,
            url_pdf=f"{PDF_PREFIX}{path.name}",
            url_page="",
            reason="file is not referenced by publications.csv",
        )
        for path in sorted(PAPERS_DIR.glob("*.pdf"))
        if path not in referenced
    ]

    return {
        "local_missing": local_missing,
        "remote_pdf": remote_pdf,
        "missing_pdf": missing_pdf,
        "browser_required": browser_required,
        "orphan_pdf": orphan_pdf,
    }


def download_file(url: str, destination: Path, timeout: int) -> None:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 publication-pdf-maintainer",
            "Accept": "application/pdf,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("content-type", "")
        data = response.read()

    if not data.startswith(b"%PDF"):
        raise ValueError(f"download did not look like a PDF: content-type={content_type!r}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", delete=False, dir=destination.parent) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    tmp_path.replace(destination)


def download_open_pdfs(publications: List[Publication], write_csv: bool, timeout: int) -> Tuple[int, int]:
    downloaded = 0
    failed = 0
    for publication in publications:
        url_pdf = publication.get("url_pdf")
        if not is_open_direct_pdf(url_pdf):
            continue

        filename = suggested_pdf_name(publication)
        destination = PAPERS_DIR / filename
        try:
            download_file(url_pdf, destination, timeout)
        except (OSError, urllib.error.URLError, ValueError) as exc:
            failed += 1
            print(f"download failed: row {publication.row_number} {publication.get('title')} ({exc})", file=sys.stderr)
            continue

        downloaded += 1
        local_url = f"{PDF_PREFIX}{filename}"
        print(f"downloaded: row {publication.row_number} -> {local_url}")
        if write_csv:
            publication.set("url_pdf", local_url)

    return downloaded, failed


def print_report(results: Dict[str, List[AuditItem]]) -> None:
    labels = [
        ("local_missing", "Local PDF path missing"),
        ("remote_pdf", "Remote paper PDF"),
        ("browser_required", "Needs logged-in browser"),
        ("missing_pdf", "No PDF known yet"),
        ("orphan_pdf", "Orphan local PDF"),
    ]
    for key, label in labels:
        items = results[key]
        print(f"\n{label}: {len(items)}")
        for item in items:
            location = f"row {item.row}" if item.row else "file"
            suggested = f" -> suggested {item.suggested_file}" if item.suggested_file else ""
            source = f" [{item.download_url}]" if item.download_url else ""
            print(f"  - {location}: {item.shortconf} | {item.title}{suggested}{source}")


def json_report(results: Dict[str, List[AuditItem]]) -> str:
    return json.dumps(
        {key: [asdict(item) for item in items] for key, items in results.items()},
        ensure_ascii=False,
        indent=2,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit and maintain local publication PDFs.")
    parser.add_argument("--csv", type=Path, default=PUBLICATIONS_CSV)
    parser.add_argument("--json", action="store_true", help="Print machine-readable audit output.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if any issue remains.")
    parser.add_argument("--download-open", action="store_true", help="Download open direct remote PDFs.")
    parser.add_argument("--write", action="store_true", help="Write CSV changes after downloads.")
    parser.add_argument("--timeout", type=int, default=120, help="Per-download timeout in seconds.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    publications = read_publications(args.csv)

    if args.download_open:
        downloaded, failed = download_open_pdfs(publications, write_csv=args.write, timeout=args.timeout)
        if args.write and downloaded:
            write_publications(args.csv, publications)
        print(f"\nDownloaded open PDFs: {downloaded}; failed: {failed}")

    results = audit(publications)
    if args.json:
        print(json_report(results))
    else:
        print_report(results)

    if args.strict and any(results.values()):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
