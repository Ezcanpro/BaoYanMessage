import argparse
import csv
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pymysql
from sqlalchemy import delete

from models import (
    Base,
    SessionLocal,
    UniversityInfo,
    engine,
    ensure_university_info_schema,
    get_database_settings,
)


DEFAULT_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "2027_universities_official.csv"
YEAR_PATTERN = re.compile(r"(20\d{2})")


def ensure_database_exists() -> None:
    settings = get_database_settings()
    connection = pymysql.connect(
        host=settings["host"],
        port=int(settings["port"]),
        user=str(settings["user"]),
        password=str(settings["password"]),
        charset="utf8mb4",
        autocommit=True,
    )

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{settings['database']}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            )
    finally:
        connection.close()


def load_records(source_path: Path) -> list[dict[str, Any]]:
    suffix = source_path.suffix.lower()

    if suffix == ".json":
        with source_path.open("r", encoding="utf-8-sig") as file:
            payload = json.load(file)
        if not isinstance(payload, list):
            raise ValueError("JSON source must be a list of objects.")
        return payload

    if suffix == ".csv":
        with source_path.open("r", encoding="utf-8-sig", newline="") as file:
            return list(csv.DictReader(file))

    if suffix in {".xlsx", ".xls"}:
        try:
            import pandas as pd
        except ImportError as exc:
            raise RuntimeError("Importing Excel files requires pandas and openpyxl.") from exc

        frame = pd.read_excel(source_path)
        return frame.to_dict(orient="records")

    raise ValueError(f"Unsupported source file: {source_path.name}")


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    school = record.get("school") or record.get("学校")
    major = record.get("major") or record.get("专业")
    info_type = record.get("type") or record.get("类型")
    year = record.get("year") or record.get("年份")
    title = record.get("title") or record.get("标题")
    url = record.get("url") or record.get("链接")
    deadline = record.get("deadline") or record.get("截止日期")
    notes = record.get("notes") or record.get("备注")

    missing_fields = [
        field_name
        for field_name, value in {
            "school": school,
            "type": info_type,
            "year": year,
            "title": title,
            "url": url,
        }.items()
        if value in (None, "")
    ]
    if missing_fields:
        raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

    return {
        "school": str(school).strip(),
        "major": str(major).strip() if major not in (None, "") else None,
        "type": str(info_type).strip(),
        "year": int(year),
        "title": str(title).strip(),
        "url": str(url).strip(),
        "deadline": parse_deadline(deadline),
        "notes": str(notes).strip() if notes not in (None, "") else None,
    }


def parse_deadline(value: Any) -> date | None:
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    normalized = str(value).strip().replace("/", "-")
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue

    raise ValueError(f"Unsupported deadline format: {value}")


def infer_target_years(source_path: Path, records: list[dict[str, Any]]) -> list[int]:
    years = sorted({int(record["year"]) for record in records if record.get("year") is not None})
    if years:
        return years

    match = YEAR_PATTERN.search(source_path.stem)
    if match:
        return [int(match.group(1))]

    return []


def import_data(source_path: Path) -> int:
    raw_records = load_records(source_path)
    records = [normalize_record(record) for record in raw_records]
    years = infer_target_years(source_path, records)

    ensure_database_exists()
    Base.metadata.create_all(bind=engine)
    ensure_university_info_schema()

    session = SessionLocal()
    try:
        if years:
            session.execute(delete(UniversityInfo).where(UniversityInfo.year.in_(years)))

        if records:
            session.add_all([UniversityInfo(**record) for record in records])

        session.commit()
        return len(records)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the school_info database and import university data.")
    parser.add_argument(
        "--source",
        default=str(DEFAULT_DATA_FILE),
        help="Path to a JSON, CSV, or Excel data file.",
    )
    args = parser.parse_args()

    source_path = Path(args.source).resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Data source not found: {source_path}")

    count = import_data(source_path)
    print(f"Imported {count} records into school_info.university_info from {source_path}.")


if __name__ == "__main__":
    main()
