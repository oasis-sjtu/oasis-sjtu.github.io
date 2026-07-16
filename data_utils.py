import ast
import csv
import json
import re
from collections import defaultdict
from functools import lru_cache
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import config


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _tianchi_dataset_id(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    parsed = urlparse(url)
    match = re.search(r"/dataset/(\d+)", parsed.path)
    if parsed.netloc.endswith("tianchi.aliyun.com") and match:
        return match.group(1)
    return None


def _dataset_metric_keys(url: Optional[str]) -> List[str]:
    if not url:
        return []
    parsed = urlparse(url)
    clean_url = parsed._replace(query="", fragment="").geturl()
    keys = [url, clean_url]
    dataset_id = _tianchi_dataset_id(url)
    if dataset_id:
        keys.extend([dataset_id, f"https://tianchi.aliyun.com/dataset/{dataset_id}"])
    return list(dict.fromkeys(keys))


@lru_cache(maxsize=1)
def load_dataset_metrics(filename=None) -> Dict[str, Dict[str, Any]]:
    filename = filename or config.DATASET_METRICS_JSON
    try:
        with open(filename, "r", encoding="utf-8") as metrics_file:
            raw_metrics = json.load(metrics_file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

    datasets = raw_metrics.get("datasets", {})
    metrics: Dict[str, Dict[str, Any]] = {}
    for key, value in datasets.items():
        if not isinstance(value, dict):
            continue
        for metric_key in _dataset_metric_keys(key) or [key]:
            metrics[metric_key] = value
    return metrics


def _format_download_count(value: Any) -> Optional[str]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return None


def _conference_key(shortconf: Optional[str]) -> Optional[str]:
    if not shortconf:
        return None
    match = re.match(r"([A-Za-z-]+)", shortconf)
    return match.group(1).upper() if match else None


def _clean_author_name(author: str) -> str:
    return re.sub(r"\s*\([^)]*\)", "", author).strip().lower()


def _author_display_name(author: str) -> str:
    return author.replace("(Co-first)", "").replace("(Corresponding)", "").strip()


def _is_template_person(name: str) -> bool:
    return name.strip().lower().startswith("template ")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "member"


def load_oasis_member_names(filename=None) -> set:
    filename = filename or config.PEOPLE_CSV
    member_names = set()

    with open(filename, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for person in reader:
            name = (person.get("name") or "").strip()
            if name and not _is_template_person(name):
                member_names.add(name.lower())

    return member_names


def _build_author_entries(authors: List[str], oasis_member_names: set) -> List[Dict[str, Any]]:
    entries = []
    for author in authors:
        display_name = _author_display_name(author)
        entries.append(
            {
                "raw": author,
                "display": display_name,
                "is_co_first": "(Co-first)" in author,
                "is_corresponding": "(Corresponding)" in author,
                "is_oasis_member": display_name.lower() in oasis_member_names,
            }
        )
    return entries


def load_publications(filename=None) -> List[Dict[str, Any]]:
    filename = filename or config.PUBLICATIONS_CSV
    oasis_member_names = load_oasis_member_names()
    dataset_metrics = load_dataset_metrics()
    fieldnames = [
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
    publications: List[Dict[str, Any]] = []

    with open(filename, "r", encoding="utf-8") as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            publication = {
                fieldnames[i]: _clean(row[i]) if i < len(row) else None
                for i in range(len(fieldnames))
            }
            try:
                publication["authors"] = ast.literal_eval(publication["authors"] or "[]")
            except (ValueError, SyntaxError):
                publication["authors"] = []
            publication["author_entries"] = _build_author_entries(
                publication["authors"],
                oasis_member_names,
            )
            publication["dataset_downloads"] = None
            publication["dataset_downloads_display"] = None
            for metric_key in _dataset_metric_keys(publication.get("url_dataset")):
                metric = dataset_metrics.get(metric_key)
                if metric:
                    publication["dataset_downloads"] = metric.get("downloads")
                    publication["dataset_downloads_display"] = _format_download_count(
                        publication["dataset_downloads"]
                    )
                    break
            publications.append(publication)

    return publications


def load_people(filename=None) -> Dict[str, List[Dict[str, str]]]:
    filename = filename or config.PEOPLE_CSV
    grouped_people: Dict[str, List[Dict[str, str]]] = defaultdict(list)

    with open(filename, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for person in reader:
            if not person.get("name"):
                continue
            role_group = person.get("group", "Members").strip() or "Members"
            grouped_people[role_group].append({k: (v or "").strip() for k, v in person.items()})

    return dict(grouped_people)


def load_people_with_publications() -> Dict[str, List[Dict[str, Any]]]:
    grouped_people = load_people()
    publications = load_publications()

    for group, members in grouped_people.items():
        for index, member in enumerate(members, 1):
            member_name = member.get("name", "").strip().lower()
            matched_publications = []

            for publication in publications:
                author_names = [_clean_author_name(author) for author in publication["authors"]]
                if member_name in author_names:
                    matched_publications.append(publication)

            conference_counts: Dict[str, int] = defaultdict(int)
            for publication in matched_publications:
                conference = _conference_key(publication.get("shortconf"))
                if conference:
                    conference_counts[conference] += 1

            member["publications"] = matched_publications
            member["publication_summary"] = [
                {"conference": conference, "count": count}
                for conference, count in sorted(
                    conference_counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ]
            member["collapse_id"] = _slugify(f"{group}-{index}-{member.get('name', '')}-publications")

    return grouped_people


def load_research(filename=None) -> List[Dict[str, str]]:
    filename = filename or config.RESEARCH_CSV
    with open(filename, newline="", encoding="utf-8") as csvfile:
        return [
            {k: (v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(csvfile)
            if row.get("title")
        ]


def load_news(filename=None, limit=None) -> Dict[str, List[Dict[str, str]]]:
    filename = filename or config.NEWS_CSV
    grouped_news: Dict[str, List[Dict[str, str]]] = defaultdict(list)

    with open(filename, newline="", encoding="utf-8") as csvfile:
        rows = [
            {k: (v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(csvfile)
            if row.get("year") and row.get("text")
        ]

    if limit:
        rows = rows[:limit]

    for item in rows:
        grouped_news[item["year"]].append(item)

    return dict(grouped_news)


def load_sponsors(filename=None) -> List[Dict[str, str]]:
    filename = filename or config.SPONSORS_CSV
    with open(filename, newline="", encoding="utf-8") as csvfile:
        return [
            {k: (v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(csvfile)
            if row.get("name")
        ]


def load_awards(filename=None) -> List[Dict[str, str]]:
    filename = filename or config.AWARDS_CSV
    with open(filename, newline="", encoding="utf-8") as csvfile:
        return [
            {k: (v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(csvfile)
            if row.get("title")
        ]
