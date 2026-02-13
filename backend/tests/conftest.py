# backend/tests/conftest.py
import os
import sys
from datetime import date

import pytest
from fastapi.testclient import TestClient

# --- IMPORTANT ---
# Ensure "backend/" is on the import path so "import app.*" works
# regardless of where pytest is launched from.
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.main import app  # noqa: E402
from app.db import get_conn  # noqa: E402
from app.auth import init_auth_tables, _hash_password, _make_jwt  # noqa: E402
from app.portfolios import init_portfolio_tables  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _test_env():
    """Make tests deterministic and avoid external dependencies."""
    # Prevent SMTP hard-fail during tests.
    os.environ.setdefault("EMAIL_MODE", "console")

    # Enable dev billing bypass so billing endpoint returns dev_upgraded instead of 501.
    os.environ.setdefault("DEV_BILLING_BYPASS", "true")

    # Optional safety net: if you set DB_NAME in the terminal, this won't overwrite it.
    os.environ.setdefault("DB_NAME", "stocks_test")


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


def _truncate_all(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            TRUNCATE TABLE
              transactions,
              portfolios,
              holdings,
              user_search_log,
              user_plan_windows,
              email_verification_tokens,
              app_users,
              sp500_index_daily,
              sp500_historical
            RESTART IDENTITY CASCADE;
            """
        )
    conn.commit()


def _ensure_min_price_tables(conn):
    """Create minimal price tables for tests (tiny seed)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sp500_historical (
              ticker TEXT NOT NULL,
              trade_date DATE NOT NULL,
              adj_close DOUBLE PRECISION NULL,
              PRIMARY KEY (ticker, trade_date)
            );
            """
        )
    conn.commit()


@pytest.fixture()
def db_seed():
    """Reset DB and seed the minimum data needed for portfolio tests."""
    init_auth_tables()
    init_portfolio_tables()

    with get_conn() as conn:
        _ensure_min_price_tables(conn)
        _truncate_all(conn)

        with conn.cursor() as cur:
            rows = [
                ("SP500", date(2024, 1, 2), 100.0),
                ("SP500", date(2024, 1, 3), 101.0),
                ("SP500", date(2024, 1, 4), 102.0),
                ("AAPL", date(2024, 1, 2), 50.0),
                ("AAPL", date(2024, 1, 3), 51.0),
                ("AAPL", date(2024, 1, 4), 52.0),
            ]
            cur.executemany(
                """
                INSERT INTO sp500_historical (ticker, trade_date, adj_close)
                VALUES (%s, %s, %s);
                """,
                rows,
            )

            pw_hash = _hash_password("TestPass123!")
            cur.execute(
                """
                INSERT INTO app_users (email, username, password_hash, is_verified)
                VALUES (%s, %s, %s, TRUE)
                RETURNING id;
                """,
                ("test@example.com", "testuser", pw_hash),
            )
            user_id = int(cur.fetchone()[0])

        conn.commit()

    token = _make_jwt(user_id=user_id, username="testuser")
    return {"user_id": user_id, "token": token}

@pytest.fixture()
def auth_headers(db_seed):
    """Authorization header for the seeded verified test user."""
    return {"Authorization": f"Bearer {db_seed['token']}"}