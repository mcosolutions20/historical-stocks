import os
import psycopg
from urllib.parse import urlparse
from dotenv import load_dotenv

# Load .env if present (local dev)
load_dotenv()


def _get_db_config():
    """
    Production-style DB config resolution:

    1. If DATABASE_URL is set, use it.
    2. Otherwise fall back to split DB_* environment variables.
    """

    database_url = os.getenv("DATABASE_URL")

    if database_url:
        parsed = urlparse(database_url)
        return {
            "host": parsed.hostname,
            "port": parsed.port or 5432,
            "dbname": parsed.path.lstrip("/"),
            "user": parsed.username,
            "password": parsed.password,
        }

    # Fallback: split env vars
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": os.getenv("DB_NAME", "stocks"),
        "user": os.getenv("DB_USER", "devuser"),
        "password": os.getenv("DB_PASSWORD", "devpass"),
    }


def get_conn():
    config = _get_db_config()

    return psycopg.connect(
        host=config["host"],
        port=config["port"],
        dbname=config["dbname"],
        user=config["user"],
        password=config["password"],
    )