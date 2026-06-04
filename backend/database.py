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
    """
    try:
        inspector = sa_inspect(eng)
        existing_cols = {c["name"] for c in inspector.get_columns("chapter_summaries")}
        if "embedding" not in existing_cols:
            with eng.connect() as conn:
                conn.execute(text("ALTER TABLE chapter_summaries ADD COLUMN embedding TEXT"))
                conn.commit()
            print("[DB migration] Added 'embedding' column to chapter_summaries.")
        else:
            print("[DB migration] 'embedding' column already present — no migration needed.")
    except Exception as exc:
        print(f"[DB migration] Warning: {exc}")
