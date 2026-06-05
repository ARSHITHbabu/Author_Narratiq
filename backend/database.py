from sqlalchemy import create_engine, text, inspect as sa_inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:///./narratiq.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_db_migrations(eng) -> None:
    """
    Apply lightweight column-addition migrations without Alembic.
    Safe to call on every startup — skips columns that already exist.
    New tables are created by Base.metadata.create_all before this runs.
    """
    inspector = sa_inspect(eng)
    existing_tables = set(inspector.get_table_names())

    def _add_col(table: str, col: str, col_def: str) -> None:
        if table not in existing_tables:
            return  # table will be created by create_all; no ALTER needed
        try:
            cols = {c["name"] for c in inspector.get_columns(table)}
            if col not in cols:
                with eng.connect() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}"))
                    conn.commit()
                print(f"[DB migration] Added '{col}' to {table}.")
        except Exception as exc:
            print(f"[DB migration] Warning ({table}.{col}): {exc}")

    # chapter_summaries
    _add_col("chapter_summaries", "embedding", "TEXT")

    # character_profiles — new structured fields
    _add_col("character_profiles", "goals",   "TEXT    DEFAULT ''")
    _add_col("character_profiles", "traits",  "TEXT    DEFAULT '[]'")
