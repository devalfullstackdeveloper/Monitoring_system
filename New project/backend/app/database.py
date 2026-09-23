import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL and all((DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)):
    DATABASE_URL = (
        f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./tracker.db"

engine_options = {}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_options)


def migrate_security_schema():
    """Add RBAC columns safely for existing deployments without Alembic yet."""
    with engine.begin() as connection:
        if DATABASE_URL.startswith("postgresql"):
            for role in ("super_admin", "manager"):
                connection.execute(text(
                    "DO $$ BEGIN ALTER TYPE userrole ADD VALUE IF NOT EXISTS :role; "
                    "EXCEPTION WHEN undefined_object THEN NULL; END $$;"
                ), {"role": role})

        inspector = inspect(connection)
        if "users" not in inspector.get_table_names():
            return
        columns = {column["name"] for column in inspector.get_columns("users")}
        if "organization_id" not in columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN organization_id INTEGER"))
        if "manager_id" not in columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN manager_id INTEGER"))
        settings_columns = {column["name"] for column in inspector.get_columns("app_settings")} if "app_settings" in inspector.get_table_names() else set()
        if "retention_days" not in settings_columns and settings_columns:
            connection.execute(text("ALTER TABLE app_settings ADD COLUMN retention_days INTEGER NOT NULL DEFAULT 90"))
        if "screenshot_masking_enabled" not in settings_columns and settings_columns:
            connection.execute(text("ALTER TABLE app_settings ADD COLUMN screenshot_masking_enabled BOOLEAN NOT NULL DEFAULT FALSE"))

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
