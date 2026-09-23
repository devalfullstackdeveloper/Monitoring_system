import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def migrate_schema():
    """Apply small, idempotent schema updates for existing installations."""
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "created_by_id" not in user_columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE users ADD COLUMN created_by_id INTEGER "
                    "REFERENCES users(id)"
                )
            )

    user_columns = {column["name"] for column in inspect(engine).get_columns("users")}
    if "parent_id" not in user_columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE users ADD COLUMN parent_id INTEGER REFERENCES users(id)")
            )
            if "created_by_id" in user_columns:
                connection.execute(
                    text("UPDATE users SET parent_id = created_by_id WHERE parent_id IS NULL")
                )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
