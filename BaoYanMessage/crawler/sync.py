import argparse
import csv
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SOURCES = BASE_DIR / "crawler" / "sources_2027.json"
DEFAULT_OFFICIAL_CSV = BASE_DIR / "data" / "2027_universities_official.csv"
DEFAULT_CANDIDATES_CSV = BASE_DIR / "data" / "2027_sync_candidates.csv"
DEFAULT_UPDATES_CSV = BASE_DIR / "data" / "2027_sync_updates.csv"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36"
)
DATE_PATTERNS = [
    re.compile(r"(20\d{2})[年\-/](\d{1,2})[月\-/](\d{1,2})日?"),
    re.compile(r"(\d{1,2})[月\-/](\d{1,2})日?"),
]
OFFICIAL_FIELDNAMES = ["school", "major", "type", "year", "title", "url", "deadline", "notes"]
CANDIDATE_FIELDNAMES = OFFICIAL_FIELDNAMES + ["publish_date", "source_id", "source_url", "status"]


@dataclass
class SourceConfig:
    id: str
    school: str
    major: str
    type: str
    year: int
    list_url: str
    allowed_keywords: list[str]
    denied_keywords: list[str]
    notes_prefix: str
    limit: int = 10


@dataclass
class CandidateRecord:
    school: str
    major: str
    type: str
    year: int
    title: str
    url: str
    deadline: str
    notes: str
    source_id: str
    source_url: str
    publish_date: str = ""
    status: str = "new"

    def to_csv_dict(self) -> dict[str, str | int]:
        return {
            "school": self.school,
            "major": self.major,
            "type": self.type,
            "year": self.year,
            "title": self.title,
            "url": self.url,
            "deadline": self.deadline,
            "notes": self.notes,
            "publish_date": self.publish_date,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "status": self.status,
        }

    def to_official_row(self) -> dict[str, str | int]:
        return {
            "school": self.school,
            "major": self.major,
            "type": self.type,
            "year": self.year,
            "title": self.title,
            "url": self.url,
            "deadline": self.deadline,
            "notes": self.notes,
        }


@dataclass
class ScrapeResult:
    candidates: list[CandidateRecord]
    skipped_before_start: int = 0
    skipped_wrong_year: int = 0


@dataclass
class SyncResult:
    all_candidates: list[CandidateRecord]
    updates: list[CandidateRecord]
    applied_count: int
    skipped_before_start: int
    skipped_wrong_year: int


def load_sources(path: Path) -> list[SourceConfig]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return [SourceConfig(**item) for item in payload]


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def ensure_csv_with_header(path: Path, fieldnames: list[str]) -> None:
    ensure_parent_dir(path)
    if path.exists():
        return

    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()


def load_existing_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def fetch_html(url: str) -> str:
    response = requests.get(url, timeout=20, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def find_candidate_links(source: SourceConfig, html: str) -> list[tuple[str, str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    candidates: list[tuple[str, str, str]] = []

    for anchor in soup.find_all("a", href=True):
        title = normalize_space(anchor.get_text(" ", strip=True))
        if not title or len(title) < 6:
            continue

        combined_text = normalize_space(anchor.parent.get_text(" ", strip=True))
        full_text = f"{title} {combined_text}"

        if not matches_keywords(full_text, source.allowed_keywords, source.denied_keywords):
            continue

        url = urljoin(source.list_url, anchor["href"].strip())
        if url in seen:
            continue

        seen.add(url)
        candidates.append((title, url, combined_text))

        if len(candidates) >= source.limit:
            break

    return candidates


def matches_keywords(text: str, allowed: Iterable[str], denied: Iterable[str]) -> bool:
    normalized = text.lower()
    allowed_hit = any(keyword.lower() in normalized for keyword in allowed)
    denied_hit = any(keyword.lower() in normalized for keyword in denied)
    return allowed_hit and not denied_hit


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def extract_deadline(*texts: str) -> str:
    merged = " ".join(text for text in texts if text)
    if not merged:
        return ""

    labeled = extract_labeled_date(merged, ["截止", "截止时间", "报名截止", "申请截止", "截止日期"])
    if labeled:
        return labeled

    if not any(marker in merged for marker in ["截止", "报名", "申请", "开放", "时间"]):
        return ""

    for pattern in DATE_PATTERNS:
        match = pattern.search(merged)
        if not match:
            continue

        groups = match.groups()
        if len(groups) == 3:
            year, month, day = groups
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"

    return ""


def extract_publish_date(title: str, snippet: str, detail_text: str, target_year: int) -> str:
    merged = " ".join(part for part in [title, snippet, detail_text] if part)
    labeled = extract_labeled_date(merged, ["发布时间", "发布于", "发布日期", "日期", "时间"])
    if labeled:
        return labeled

    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(merged):
            groups = match.groups()
            if len(groups) == 3:
                year, month, day = groups
                parsed = date(int(year), int(month), int(day))
                if parsed.year in {target_year - 1, target_year}:
                    return parsed.isoformat()

    return ""


def extract_labeled_date(text: str, labels: Iterable[str]) -> str:
    for label in labels:
        pattern = re.compile(
            rf"{re.escape(label)}[^0-9]{{0,12}}(20\d{{2}})[年\-/](\d{{1,2}})[月\-/](\d{{1,2}})日?"
        )
        match = pattern.search(text)
        if match:
            year, month, day = match.groups()
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return ""


def build_notes(source: SourceConfig, snippet: str, detail_text: str) -> str:
    basis = snippet if len(snippet) >= len(detail_text) else detail_text
    basis = normalize_space(basis)
    if len(basis) > 88:
        basis = basis[:88].rstrip() + "..."
    if basis:
        return f"{source.notes_prefix}；{basis}"
    return source.notes_prefix


def contains_target_year(*texts: str, target_year: int) -> bool:
    merged = " ".join(text for text in texts if text)
    markers = [str(target_year), to_chinese_digits(target_year)]
    return any(marker in merged for marker in markers)


def to_chinese_digits(year: int) -> str:
    mapping = {"0": "零", "1": "一", "2": "二", "3": "三", "4": "四", "5": "五", "6": "六", "7": "七", "8": "八", "9": "九"}
    return "".join(mapping[digit] for digit in str(year))


def parse_iso_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def is_publish_date_allowed(publish_date: str, monitor_start: date | None) -> bool:
    if monitor_start is None:
        return True
    parsed = parse_iso_date(publish_date)
    if parsed is None:
        return True
    return parsed >= monitor_start


def scrape_source(source: SourceConfig, monitor_start: date | None) -> ScrapeResult:
    html = fetch_html(source.list_url)
    link_candidates = find_candidate_links(source, html)
    result = ScrapeResult(candidates=[])

    for title, url, snippet in link_candidates:
        detail_text = ""
        try:
            detail_html = fetch_html(url)
            detail_soup = BeautifulSoup(detail_html, "html.parser")
            detail_text = normalize_space(detail_soup.get_text(" ", strip=True))
        except Exception:
            detail_text = ""

        if not contains_target_year(title, snippet, detail_text, target_year=source.year):
            result.skipped_wrong_year += 1
            continue

        publish_date = extract_publish_date(title, snippet, detail_text, target_year=source.year)
        if publish_date and not is_publish_date_allowed(publish_date, monitor_start):
            result.skipped_before_start += 1
            continue

        deadline = extract_deadline(title, snippet, detail_text)
        notes = build_notes(source, snippet, detail_text)
        result.candidates.append(
            CandidateRecord(
                school=source.school,
                major=source.major,
                type=source.type,
                year=source.year,
                title=title,
                url=url,
                deadline=deadline,
                notes=notes,
                source_id=source.id,
                source_url=source.list_url,
                publish_date=publish_date,
            )
        )

    return result


def compare_with_existing(candidates: list[CandidateRecord], existing_rows: list[dict[str, str]]) -> list[CandidateRecord]:
    existing_by_url = {row.get("url", "").strip(): row for row in existing_rows if row.get("url")}
    existing_by_title = {row.get("title", "").strip(): row for row in existing_rows if row.get("title")}

    updates: list[CandidateRecord] = []
    for item in candidates:
        existing = existing_by_url.get(item.url) or existing_by_title.get(item.title)
        if not existing:
            item.status = "new"
            updates.append(item)
            continue

        changed = []
        for field in OFFICIAL_FIELDNAMES:
            old_value = str(existing.get(field, "") or "").strip()
            new_value = str(getattr(item, field) or "").strip()
            if old_value != new_value:
                changed.append(field)

        if changed:
            item.status = "changed:" + ",".join(changed)
            updates.append(item)

    return updates


def apply_updates(existing_rows: list[dict[str, str]], updates: list[CandidateRecord]) -> tuple[list[dict[str, str]], int]:
    merged_rows = [normalize_existing_row(row) for row in existing_rows]
    applied_count = 0

    for item in updates:
        replacement = item.to_official_row()
        row_index = find_existing_index(merged_rows, item)
        if row_index >= 0:
            merged_rows[row_index] = replacement
        else:
            merged_rows.append(replacement)
        applied_count += 1

    merged_rows.sort(key=sort_key_for_official_row)
    return merged_rows, applied_count


def normalize_existing_row(row: dict[str, str]) -> dict[str, str]:
    return {field: str(row.get(field, "") or "").strip() for field in OFFICIAL_FIELDNAMES}


def find_existing_index(rows: list[dict[str, str]], item: CandidateRecord) -> int:
    for index, row in enumerate(rows):
        if row.get("url") == item.url or row.get("title") == item.title:
            return index
    return -1


def sort_key_for_official_row(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("school", "")),
        str(row.get("major", "")),
        str(row.get("type", "")),
        str(row.get("deadline", "9999-12-31") or "9999-12-31"),
        str(row.get("title", "")),
    )


def write_candidate_csv(path: Path, rows: list[CandidateRecord]) -> None:
    ensure_parent_dir(path)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CANDIDATE_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_csv_dict())


def write_official_csv(path: Path, rows: list[dict[str, str]]) -> None:
    ensure_parent_dir(path)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=OFFICIAL_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in OFFICIAL_FIELDNAMES})


def backup_file(path: Path) -> None:
    if not path.exists():
        return
    backup_path = path.with_suffix(path.suffix + ".bak")
    backup_path.write_bytes(path.read_bytes())


def run_sync(
    sources_path: Path,
    official_path: Path,
    candidates_out: Path,
    updates_out: Path,
    monitor_start: date | None,
    auto_apply: bool,
) -> SyncResult:
    ensure_csv_with_header(official_path, OFFICIAL_FIELDNAMES)
    sources = load_sources(sources_path)
    existing_rows = load_existing_rows(official_path)

    all_candidates: list[CandidateRecord] = []
    skipped_before_start = 0
    skipped_wrong_year = 0

    for source in sources:
        try:
            scrape_result = scrape_source(source, monitor_start=monitor_start)
            print(
                f"[{source.id}] scraped {len(scrape_result.candidates)} candidate rows "
                f"(skipped_year={scrape_result.skipped_wrong_year}, skipped_start={scrape_result.skipped_before_start})"
            )
            all_candidates.extend(scrape_result.candidates)
            skipped_before_start += scrape_result.skipped_before_start
            skipped_wrong_year += scrape_result.skipped_wrong_year
        except Exception as exc:
            print(f"[{source.id}] failed: {exc}")

    write_candidate_csv(candidates_out, all_candidates)
    updates = compare_with_existing(all_candidates, existing_rows)
    write_candidate_csv(updates_out, updates)

    applied_count = 0
    if auto_apply and updates:
        merged_rows, applied_count = apply_updates(existing_rows, updates)
        backup_file(official_path)
        write_official_csv(official_path, merged_rows)

    return SyncResult(
        all_candidates=all_candidates,
        updates=updates,
        applied_count=applied_count,
        skipped_before_start=skipped_before_start,
        skipped_wrong_year=skipped_wrong_year,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Automatic sync crawler for BAOYAN notices.")
    parser.add_argument("--sources", default=str(DEFAULT_SOURCES), help="Path to crawler source config JSON.")
    parser.add_argument("--official", default=str(DEFAULT_OFFICIAL_CSV), help="Path to the official CSV.")
    parser.add_argument("--candidates-out", default=str(DEFAULT_CANDIDATES_CSV), help="Output path for scraped candidates.")
    parser.add_argument("--updates-out", default=str(DEFAULT_UPDATES_CSV), help="Output path for changed or new candidates.")
    parser.add_argument(
        "--monitor-start",
        default="",
        help="Only keep notices published on or after this date (YYYY-MM-DD). Leave empty to monitor immediately.",
    )
    parser.add_argument(
        "--auto-apply",
        action="store_true",
        help="Automatically merge new and changed records into the official CSV.",
    )
    args = parser.parse_args()

    source_path = Path(args.sources).resolve()
    official_path = Path(args.official).resolve()
    candidates_out = Path(args.candidates_out).resolve()
    updates_out = Path(args.updates_out).resolve()
    monitor_start = date.fromisoformat(args.monitor_start) if args.monitor_start else None

    result = run_sync(
        sources_path=source_path,
        official_path=official_path,
        candidates_out=candidates_out,
        updates_out=updates_out,
        monitor_start=monitor_start,
        auto_apply=args.auto_apply,
    )

    print(f"Wrote {len(result.all_candidates)} scraped candidates to {candidates_out}")
    print(f"Wrote {len(result.updates)} pending updates to {updates_out}")
    print(f"Skipped {result.skipped_wrong_year} rows because they did not mention the target year")
    if monitor_start is not None:
        print(f"Skipped {result.skipped_before_start} rows because they were published before {monitor_start.isoformat()}")
    if args.auto_apply:
        print(f"Applied {result.applied_count} updates to {official_path}")


if __name__ == "__main__":
    main()
