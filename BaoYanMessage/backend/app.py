from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from sqlalchemy import asc, desc
from sqlalchemy.exc import SQLAlchemyError

from models import SessionLocal, UniversityInfo, ensure_university_info_schema


BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
OFFICIAL_CSV_PATH = BASE_DIR / "data" / "2027_universities_official.csv"

app = Flask(
    __name__,
    static_folder=str(FRONTEND_DIR),
    static_url_path="/static",
)

SORTABLE_FIELDS = {
    "id": UniversityInfo.id,
    "school": UniversityInfo.school,
    "major": UniversityInfo.major,
    "type": UniversityInfo.type,
    "year": UniversityInfo.year,
    "deadline": UniversityInfo.deadline,
    "title": UniversityInfo.title,
}

ensure_university_info_schema()


@app.get("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/health")
def health_check():
    return jsonify({"status": "ok"})


@app.get("/schools")
def get_schools():
    school = request.args.get("school", "").strip()
    major = request.args.get("major", "").strip()
    info_type = request.args.get("type", "").strip()
    year = request.args.get("year", "").strip()
    sort_by = request.args.get("sort_by", "deadline").strip().lower()
    order = request.args.get("order", "asc").strip().lower()

    session = SessionLocal()
    try:
        query = session.query(UniversityInfo)

        if school:
            query = query.filter(UniversityInfo.school.contains(school))

        if major:
            query = query.filter(UniversityInfo.major.contains(major))

        if info_type:
            query = query.filter(UniversityInfo.type == info_type)

        if year:
            try:
                query = query.filter(UniversityInfo.year == int(year))
            except ValueError:
                return jsonify({"error": "Invalid year parameter."}), 400

        sort_column = SORTABLE_FIELDS.get(sort_by, UniversityInfo.deadline)
        sort_direction = desc if order == "desc" else asc
        rows = query.order_by(sort_direction(sort_column), asc(UniversityInfo.id)).all()
        return jsonify({"count": len(rows), "data": [row.to_dict() for row in rows]})
    except SQLAlchemyError as exc:
        return jsonify({"error": f"Database query failed: {exc.__class__.__name__}"}), 500
    finally:
        session.close()


@app.post("/admin/import-official-csv")
def import_official_csv():
    if not OFFICIAL_CSV_PATH.exists():
        return jsonify({"error": f"Official CSV not found: {OFFICIAL_CSV_PATH.name}"}), 404

    try:
        from db_setup import import_data
    except ModuleNotFoundError as exc:
        return (
            jsonify(
                {
                    "error": "Import dependencies are missing.",
                    "details": f"{exc.name} is not installed.",
                }
            ),
            500,
        )
    except Exception as exc:
        return jsonify({"error": f"Failed to load importer: {exc.__class__.__name__}"}), 500

    try:
        count = import_data(OFFICIAL_CSV_PATH)
        return jsonify(
            {
                "message": "Official CSV imported successfully.",
                "source": OFFICIAL_CSV_PATH.name,
                "count": count,
            }
        )
    except FileNotFoundError:
        return jsonify({"error": f"Official CSV not found: {OFFICIAL_CSV_PATH.name}"}), 404
    except Exception as exc:
        return jsonify({"error": f"Import failed: {exc}"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
