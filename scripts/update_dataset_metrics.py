#!/usr/bin/env python3
import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
PUBLICATIONS_CSV = ROOT / "static" / "publications.csv"
METRICS_JSON = ROOT / "static" / "dataset_metrics.json"
DATASET_URL_INDEX = 8


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def tianchi_dataset_id(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    parsed = urlparse(url)
    match = re.search(r"/dataset/(\d+)", parsed.path)
    if parsed.netloc.endswith("tianchi.aliyun.com") and match:
        return match.group(1)
    return None


def canonical_tianchi_url(dataset_id: str) -> str:
    return f"https://tianchi.aliyun.com/dataset/{dataset_id}"


def dataset_ids_from_publications() -> List[str]:
    dataset_ids: List[str] = []
    seen = set()
    with PUBLICATIONS_CSV.open(newline="", encoding="utf-8") as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            if len(row) <= DATASET_URL_INDEX:
                continue
            dataset_id = tianchi_dataset_id(row[DATASET_URL_INDEX].strip())
            if dataset_id and dataset_id not in seen:
                dataset_ids.append(dataset_id)
                seen.add(dataset_id)
    return dataset_ids


def load_existing_metrics() -> Dict[str, Any]:
    if not METRICS_JSON.exists():
        return {"updated_at": None, "datasets": {}}
    try:
        with METRICS_JSON.open(encoding="utf-8") as metrics_file:
            metrics = json.load(metrics_file)
    except json.JSONDecodeError:
        return {"updated_at": None, "datasets": {}}
    metrics.setdefault("datasets", {})
    return metrics


def normalize_download_count(value: Any) -> Optional[int]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def fetch_tianchi_download_count(page: Any, dataset_id: str, timeout_ms: int) -> int:
    url = canonical_tianchi_url(dataset_id)
    result: Dict[str, int] = {}

    def handle_response(response: Any) -> None:
        if "/api/notebook/dataDetail" not in response.url:
            return
        try:
            body = response.json()
        except Exception:
            return
        downloads = normalize_download_count((body.get("data") or {}).get("datalabDownloadCount"))
        if downloads is not None:
            result["downloads"] = downloads

    try:
        page.on("response", handle_response)
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:
            pass

        deadline = time.monotonic() + timeout_ms / 1000
        while "downloads" not in result and time.monotonic() < deadline:
            page.wait_for_timeout(250)
    finally:
        page.remove_listener("response", handle_response)

    if "downloads" not in result:
        raise RuntimeError(f"download count was not found for dataset {dataset_id}")
    return result["downloads"]


def update_metrics(timeout_ms: int, headless: bool) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is required. Install it with: python -m pip install playwright", file=sys.stderr)
        return 2

    dataset_ids = dataset_ids_from_publications()
    existing = load_existing_metrics()
    datasets = existing.get("datasets", {})
    now = utc_now()
    failures = 0

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(locale="zh-CN")
        page = context.new_page()
        for dataset_id in dataset_ids:
            url = canonical_tianchi_url(dataset_id)
            try:
                downloads = fetch_tianchi_download_count(page, dataset_id, timeout_ms)
                datasets[url] = {
                    "source": "tianchi",
                    "dataset_id": dataset_id,
                    "downloads": downloads,
                    "updated_at": now,
                }
                print(f"{dataset_id}: {downloads}")
            except Exception as exc:
                failures += 1
                previous = datasets.get(url, {})
                previous.update(
                    {
                        "source": "tianchi",
                        "dataset_id": dataset_id,
                        "last_error": str(exc),
                        "last_error_at": now,
                    }
                )
                datasets[url] = previous
                print(f"{dataset_id}: {exc}", file=sys.stderr)
        context.close()
        browser.close()

    output = {"updated_at": now, "datasets": datasets}
    METRICS_JSON.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if failures:
        print(f"Completed with {failures} dataset refresh failure(s); previous values were preserved.", file=sys.stderr)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh Tianchi dataset download counts.")
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--headed", action="store_true", help="Run Chromium with a visible window.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return update_metrics(timeout_ms=args.timeout_ms, headless=not args.headed)


if __name__ == "__main__":
    raise SystemExit(main())
