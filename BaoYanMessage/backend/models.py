import os
from datetime import date

from sqlalchemy import Date, Integer, String, Text, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def get_database_settings() -> dict[str, str | int]:
    return {
        "host": os.getenv("DB_HOST", "127.0.0.1"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", "123456"),
        "database": os.getenv("DB_NAME", "school_info"),
    }


def get_database_url(include_database: bool = True) -> str:
    settings = get_database_settings()
    database = f"/{settings['database']}" if include_database else ""
    return (
        f"mysql+pymysql://{settings['user']}:{settings['password']}"
        f"@{settings['host']}:{settings['port']}{database}?charset=utf8mb4"
    )


class Base(DeclarativeBase):
    pass


class UniversityInfo(Base):
    __tablename__ = "university_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    school: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    major: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(255), nullable=False)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "id": self.id,
            "school": self.school,
            "major": self.major,
            "type": self.type,
            "year": self.year,
            "title": self.title,
            "url": self.url,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "notes": self.notes,
        }


engine = create_engine(
    get_database_url(),
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def ensure_university_info_schema() -> None:
    """Ensure the runtime table schema matches the current model."""
    try:
        inspector = inspect(engine)

        if not inspector.has_table("university_info"):
            return

        existing_columns = {column["name"] for column in inspector.get_columns("university_info")}

        with engine.begin() as connection:
            if "major" not in existing_columns:
                connection.execute(
                    text("ALTER TABLE university_info ADD COLUMN major VARCHAR(255) NULL AFTER school")
                )
    except Exception:
        return
