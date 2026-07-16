#!/usr/bin/env python3
import argparse
import concurrent.futures
import csv
import json
import re
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import parse_qs, urlparse


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

PUBLICATION_LINK_FIELDS = [
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

ARTIFACT_TOKENS = {
    "ae",
    "artifact",
    "artifacts",
    "evaluation",
    "submission",
    "opensource",
    "open-source",
}

CODE_HOSTS = {
    "github.com",
    "gitlab.com",
    "bitbucket.org",
    "sourceforge.net",
}

DATASET_HOSTS = {
    "tianchi.aliyun.com",
    "zenodo.org",
    "figshare.com",
    "huggingface.co",
    "kaggle.com",
    "dataverse.harvard.edu",
    "osf.io",
    "data.mendeley.com",
    "datahub.io",
}

ANTI_BOT_403_HOSTS = {
    "doi.org",
    "dl.acm.org",
    "ieeexplore.ieee.org",
}

URL_PATTERN = re.compile(rb"https?://[^\s<>()\"'{}|\\^\[\]`]+")


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


@dataclass
class LinkFinding:
    row: int
    shortconf: str
    title: str
    pdf: str
    kind: str
    url: str
    csv_value: str
    reason: str


@dataclass
class LinkCheckIssue:
    row: int
    shortconf: str
    title: str
    field: str
    url: str
    reason: str


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


def local_reference_path(value: str) -> Optional[Path]:
    if value.startswith("../"):
        return (ROOT / value.replace("../", "", 1)).resolve()
    if value.startswith("/"):
        return (ROOT / value.lstrip("/")).resolve()
    return None


def is_remote_pdf(url_pdf: str) -> bool:
    parsed = urlparse(url_pdf)
    return parsed.scheme in {"http", "https"} and parsed.path.lower().endswith(".pdf")


def canonical_url(url: str) -> str:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    if host == "tianchi.aliyun.com":
        data_id = None
        dataset_match = re.search(r"/dataset/(\d+)", parsed.path)
        if dataset_match:
            data_id = dataset_match.group(1)
        elif parsed.path == "/dataset/dataDetail":
            data_id = parse_qs(parsed.query).get("dataId", [None])[0]
        if data_id:
            return f"https://tianchi.aliyun.com/dataset/{data_id}"

    path = re.sub(r"/+$", "", parsed.path)
    scheme = "https" if parsed.scheme in {"http", "https"} else parsed.scheme
    return parsed._replace(scheme=scheme, netloc=host, path=path, params="", query="", fragment="").geturl().lower()


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


def publications_by_local_pdf(publications: Iterable[Publication]) -> Dict[Path, Publication]:
    mapping: Dict[Path, Publication] = {}
    for publication in publications:
        url_pdf = publication.get("url_pdf")
        if is_local_pdf(url_pdf):
            mapping[local_pdf_path(url_pdf).resolve()] = publication
    return mapping


def write_publications(path: Path, publications: Iterable[Publication]) -> None:
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile, lineterminator="\n")
        writer.writerows(publication.row for publication in publications)


def publication_link_entries(publications: Iterable[Publication]) -> List[Tuple[Publication, str, str]]:
    entries: List[Tuple[Publication, str, str]] = []
    for publication in publications:
        for field in PUBLICATION_LINK_FIELDS:
            value = publication.get(field)
            if value:
                entries.append((publication, field, value))
    return entries


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


def extract_urls_from_pdf(path: Path) -> List[str]:
    data = path.read_bytes()
    urls = set()
    for match in URL_PATTERN.finditer(data):
        raw = match.group(0).decode("latin-1", errors="ignore")
        raw = raw.replace("\\/", "/").replace("\\)", "").replace("\\(", "")
        raw = raw.rstrip(".,;:)]}>")
        if raw:
            urls.add(raw)
    return sorted(urls)


def title_tokens(publication: Publication) -> Set[str]:
    return {
        token
        for token in clean_slug(publication.get("title")).split("-")
        if len(token) >= 4 and token not in STOPWORDS
    }


def looks_like_project_link(url: str, publication: Publication) -> bool:
    parsed = urlparse(url)
    path_tokens = set(re.findall(r"[a-z0-9]+", parsed.path.lower()))
    if not path_tokens:
        return False
    if path_tokens & ARTIFACT_TOKENS:
        return True
    return bool(path_tokens & title_tokens(publication))


def classify_candidate_url(url: str, publication: Publication) -> Optional[str]:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    if host in CODE_HOSTS:
        return "code" if looks_like_project_link(url, publication) else None

    if host in DATASET_HOSTS:
        if host == "huggingface.co" and not parsed.path.startswith("/datasets/"):
            return None
        if host == "kaggle.com" and "/datasets/" not in parsed.path:
            return None
        if host == "tianchi.aliyun.com" and "/dataset/" not in parsed.path:
            return None
        return "dataset"

    return None


def is_recorded(candidate: str, csv_value: str) -> bool:
    if not csv_value:
        return False
    candidate_url = canonical_url(candidate)
    csv_url = canonical_url(csv_value)
    return candidate_url == csv_url or candidate_url.startswith(f"{csv_url}/") or csv_url.startswith(f"{candidate_url}/")


def link_findings(publications: List[Publication], only_paths: Optional[Set[Path]] = None) -> List[LinkFinding]:
    publication_by_pdf = publications_by_local_pdf(publications)
    findings: List[LinkFinding] = []

    for pdf_path, publication in sorted(publication_by_pdf.items(), key=lambda item: str(item[0])):
        if only_paths and pdf_path not in only_paths:
            continue
        if not pdf_path.exists():
            continue

        for url in extract_urls_from_pdf(pdf_path):
            kind = classify_candidate_url(url, publication)
            if not kind:
                continue

            field = "url_code" if kind == "code" else "url_dataset"
            csv_value = publication.get(field)
            if not csv_value:
                reason = f"candidate {kind} link found in PDF, but {field} is empty"
            elif is_recorded(url, csv_value):
                continue
            elif kind == "code" and looks_like_project_link(csv_value, publication):
                continue
            else:
                reason = f"candidate {kind} link is not recorded in {field}"

            findings.append(
                LinkFinding(
                    row=publication.row_number,
                    shortconf=publication.get("shortconf"),
                    title=publication.get("title"),
                    pdf=str(pdf_path.relative_to(ROOT)),
                    kind=kind,
                    url=url,
                    csv_value=csv_value,
                    reason=reason,
                )
            )

    return findings


def blocking_audit_items(results: Dict[str, List[AuditItem]]) -> Dict[str, List[AuditItem]]:
    return {
        key: results[key]
        for key in ("local_missing", "remote_pdf", "browser_required", "orphan_pdf")
        if results[key]
    }


def check_local_link(publication: Publication, field: str, value: str) -> Optional[LinkCheckIssue]:
    path = local_reference_path(value)
    if not path:
        return None
    try:
        path.relative_to(ROOT)
    except ValueError:
        return LinkCheckIssue(
            row=publication.row_number,
            shortconf=publication.get("shortconf"),
            title=publication.get("title"),
            field=field,
            url=value,
            reason="local link points outside the repository",
        )
    if path.exists():
        return None
    return LinkCheckIssue(
        row=publication.row_number,
        shortconf=publication.get("shortconf"),
        title=publication.get("title"),
        field=field,
        url=value,
        reason="local linked file does not exist",
    )


def check_remote_url(url: str, timeout: int) -> Optional[str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    last_error = None
    for method in ("HEAD", "GET"):
        headers = {
            "User-Agent": "Mozilla/5.0 publication-link-checker",
            "Accept": "text/html,application/pdf,*/*",
        }
        if method == "GET":
            headers["Range"] = "bytes=0-1023"
        request = urllib.request.Request(url, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = response.getcode()
                if 200 <= status < 400:
                    if method == "GET":
                        response.read(1024)
                    return None
                last_error = f"HTTP {status}"
        except urllib.error.HTTPError as exc:
            if exc.code == 403 and host in ANTI_BOT_403_HOSTS:
                return None
            last_error = f"HTTP {exc.code}"
            if method == "HEAD":
                continue
        except urllib.error.URLError as exc:
            last_error = str(exc.reason)
            if method == "HEAD":
                continue
        except TimeoutError:
            last_error = "timeout"
            if method == "HEAD":
                continue
        except OSError as exc:
            last_error = str(exc)
            if method == "HEAD":
                continue

    return last_error or "unreachable"


def check_publication_links(
    publications: List[Publication],
    timeout: int,
    workers: int,
) -> List[LinkCheckIssue]:
    issues: List[LinkCheckIssue] = []
    remote_tasks: Dict[str, List[Tuple[Publication, str, str]]] = {}

    for publication, field, value in publication_link_entries(publications):
        local_issue = check_local_link(publication, field, value)
        if local_issue:
            issues.append(local_issue)
            continue

        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"}:
            remote_tasks.setdefault(value, []).append((publication, field, value))

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_to_url = {
            executor.submit(check_remote_url, url, timeout): url
            for url in sorted(remote_tasks)
        }
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                reason = future.result()
            except Exception as exc:
                reason = str(exc)
            if not reason:
                continue
            for publication, field, value in remote_tasks[url]:
                issues.append(
                    LinkCheckIssue(
                        row=publication.row_number,
                        shortconf=publication.get("shortconf"),
                        title=publication.get("title"),
                        field=field,
                        url=value,
                        reason=reason,
                    )
                )

    return sorted(issues, key=lambda issue: (issue.row, issue.field, issue.url))


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


def print_link_findings(findings: List[LinkFinding]) -> None:
    print(f"\nCode/dataset candidates from PDFs: {len(findings)}")
    for finding in findings:
        csv_value = f" | csv={finding.csv_value}" if finding.csv_value else ""
        print(
            f"  - row {finding.row}: {finding.shortconf} | {finding.kind} | "
            f"{finding.url}{csv_value} | {finding.reason}"
        )


def print_link_check_issues(issues: List[LinkCheckIssue]) -> None:
    print(f"\nPublication link validity failures: {len(issues)}")
    for issue in issues:
        print(
            f"  - row {issue.row}: {issue.shortconf} | {issue.field} | "
            f"{issue.url} | {issue.reason}"
        )


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
    parser.add_argument("--extract-links", action="store_true", help="Scan local PDFs for code/dataset candidate links.")
    parser.add_argument("--check-links", action="store_true", help="Check all publication links for local existence or remote reachability.")
    parser.add_argument("--download-open", action="store_true", help="Download open direct remote PDFs.")
    parser.add_argument("--write", action="store_true", help="Write CSV changes after downloads.")
    parser.add_argument("--timeout", type=int, default=120, help="Per-download timeout in seconds.")
    parser.add_argument("--link-timeout", type=int, default=30, help="Per-link timeout in seconds.")
    parser.add_argument("--link-workers", type=int, default=4, help="Concurrent workers for link checks.")
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
    link_issues = check_publication_links(publications, args.link_timeout, args.link_workers) if args.check_links else []
    if args.json:
        payload = {key: [asdict(item) for item in items] for key, items in results.items()}
        if args.extract_links:
            payload["link_findings"] = [asdict(item) for item in link_findings(publications)]
        if args.check_links:
            payload["link_issues"] = [asdict(item) for item in link_issues]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_report(results)
        if args.extract_links:
            print_link_findings(link_findings(publications))
        if args.check_links:
            print_link_check_issues(link_issues)

    if args.strict and (any(results.values()) or link_issues):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
