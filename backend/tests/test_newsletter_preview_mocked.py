import pytest
from app.db import get_conn


from datetime import datetime, timedelta, timezone

def _set_user_pro_and_verified(user_id: int):
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=24)

    with get_conn() as conn:
        with conn.cursor() as cur:
            # ensure user is verified
            cur.execute("UPDATE app_users SET is_verified=TRUE WHERE id=%s;", (user_id,))

            # ensure plan window exists and is pro with counters reset
            cur.execute(
                """
                INSERT INTO user_plan_windows (user_id, plan, window_start, window_end, searches_used, newsletters_sent)
                VALUES (%s, 'pro', %s, %s, 0, 0)
                ON CONFLICT (user_id) DO UPDATE SET
                  plan='pro',
                  window_start=EXCLUDED.window_start,
                  window_end=EXCLUDED.window_end,
                  searches_used=0,
                  newsletters_sent=0,
                  updated_at=NOW();
                """,
                (user_id, now, window_end),
            )
        conn.commit()


def _get_auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def test_newsletter_preview_consumes_limit(monkeypatch, client, db_seed):
    """
    Production-style integration test:
      - hits FastAPI endpoint
      - uses real DB
      - enforces pro + quota
      - mocks OpenAI call so no API key required
    """
    user_id = db_seed["user_id"]
    token = db_seed["token"]

    _set_user_pro_and_verified(user_id)

    # IMPORTANT:
    # main.py imports generate_newsletter as: `from .newsletter import generate_newsletter`
    # so we patch `app.main.generate_newsletter` (not app.newsletter.generate_newsletter)
    def fake_generate_newsletter(user_id: int, email: str):
        return {"newsletter": "FAKE NEWSLETTER", "generated_at": "2026-02-12T00:00:00Z"}

    monkeypatch.setattr("app.main.generate_newsletter", fake_generate_newsletter)

    # 1st call: ok, remaining should be 1
    r1 = client.get("/newsletter/preview", headers=_get_auth_headers(token))
    assert r1.status_code == 200
    j1 = r1.json()
    assert j1["newsletter"] == "FAKE NEWSLETTER"
    assert j1["remaining"] == 1

    # 2nd call: ok, remaining should be 0
    r2 = client.get("/newsletter/preview", headers=_get_auth_headers(token))
    assert r2.status_code == 200
    j2 = r2.json()
    assert j2["remaining"] == 0

    # 3rd call: should be blocked by your limit
    r3 = client.get("/newsletter/preview", headers=_get_auth_headers(token))
    assert r3.status_code == 429