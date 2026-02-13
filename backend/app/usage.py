from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from fastapi import HTTPException
from .db import get_conn

FREE_LIMIT = 5
PRO_LIMIT = 20
PRO_NEWSLETTER_LIMIT = 2


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_plan_window(user_id: int) -> Dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT plan, window_start, window_end, searches_used, newsletters_sent
                FROM user_plan_windows
                WHERE user_id = %s
                LIMIT 1;
                """,
                (user_id,),
            )
            row = cur.fetchone()

    if not row:
        return reset_window(user_id, "free")

    plan, window_start, window_end, used, newsletters_sent = row
    return {
        "plan": plan,
        "window_start": window_start,
        "window_end": window_end,
        "searches_used": int(used),
        "newsletters_sent": int(newsletters_sent or 0),
        "limit": PRO_LIMIT if plan == "pro" else FREE_LIMIT,
        "newsletter_limit": PRO_NEWSLETTER_LIMIT,
    }


def reset_window(user_id: int, plan: str) -> Dict[str, Any]:
    now = _utcnow()
    window_end = now + timedelta(hours=24)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_plan_windows (user_id, plan, window_start, window_end, searches_used, newsletters_sent)
                VALUES (%s, %s, %s, %s, 0, 0)
                ON CONFLICT (user_id) DO UPDATE SET
                  plan = EXCLUDED.plan,
                  window_start = EXCLUDED.window_start,
                  window_end = EXCLUDED.window_end,
                  searches_used = 0,
                  newsletters_sent = 0,
                  updated_at = NOW()
                RETURNING plan, window_start, window_end, searches_used, newsletters_sent;
                """,
                (user_id, plan, now, window_end),
            )
            row = cur.fetchone()
        conn.commit()

    plan, ws, we, used, newsletters_sent = row
    return {
        "plan": plan,
        "window_start": ws,
        "window_end": we,
        "searches_used": int(used),
        "newsletters_sent": int(newsletters_sent or 0),
        "limit": PRO_LIMIT if plan == "pro" else FREE_LIMIT,
        "newsletter_limit": PRO_NEWSLETTER_LIMIT,
    }


def maybe_roll_window(user_id: int) -> Dict[str, Any]:
    pw = get_plan_window(user_id)
    now = _utcnow()

    if pw["window_end"] is not None and now >= pw["window_end"]:
        # Preserve your current behavior: pro reverts to free after window ends
        next_plan = "free" if pw["plan"] == "pro" else pw["plan"]
        return reset_window(user_id, next_plan)

    return pw


def consume_newsletter_generation(*, user_id: int, is_verified: bool) -> Dict[str, Any]:
    """
    Enforce + increment newsletters_sent atomically.
    Call this BEFORE generating a newsletter.
    """
    if not is_verified:
        raise HTTPException(status_code=403, detail="email not verified")

    pw = maybe_roll_window(user_id)

    if pw["plan"] != "pro":
        raise HTTPException(status_code=403, detail="Newsletter is available for Pro users only.")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE user_plan_windows
                SET newsletters_sent = newsletters_sent + 1,
                    updated_at = NOW()
                WHERE user_id = %s
                  AND plan = 'pro'
                  AND newsletters_sent < %s
                RETURNING newsletters_sent, window_end;
                """,
                (user_id, PRO_NEWSLETTER_LIMIT),
            )
            row = cur.fetchone()
        conn.commit()

    if not row:
        raise HTTPException(
            status_code=429,
            detail=f"Newsletter limit reached ({PRO_NEWSLETTER_LIMIT} per 24h window).",
        )

    newsletters_sent, window_end = row
    remaining = PRO_NEWSLETTER_LIMIT - int(newsletters_sent or 0)
    return {
        "newsletters_sent": int(newsletters_sent or 0),
        "remaining": max(0, remaining),
        "window_end": window_end,
        "newsletter_limit": PRO_NEWSLETTER_LIMIT,
    }


def enforce_and_increment(
    *,
    user_id: int,
    is_verified: bool,
    mode: str,
    start_date,
    end_date,
    ticker: Optional[str] = None,
    performance: Optional[str] = None,
    quantity: Optional[int] = None,
) -> Dict[str, Any]:
    if not is_verified:
        raise HTTPException(status_code=403, detail="email not verified")

    pw = maybe_roll_window(user_id)
    limit = PRO_LIMIT if pw["plan"] == "pro" else FREE_LIMIT

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Atomic increment only if under limit
            cur.execute(
                """
                UPDATE user_plan_windows
                SET searches_used = searches_used + 1,
                    updated_at = NOW()
                WHERE user_id = %s
                  AND searches_used < %s
                RETURNING plan, window_start, window_end, searches_used, newsletters_sent;
                """,
                (user_id, limit),
            )
            updated = cur.fetchone()

            if not updated:
                # Ensure row exists (should, but keep your safety behavior)
                cur.execute("SELECT plan FROM user_plan_windows WHERE user_id=%s LIMIT 1;", (user_id,))
                exists = cur.fetchone()
                if not exists:
                    reset_window(user_id, "free")
                    # retry once after creating row
                    cur.execute(
                        """
                        UPDATE user_plan_windows
                        SET searches_used = searches_used + 1,
                            updated_at = NOW()
                        WHERE user_id = %s
                          AND searches_used < %s
                        RETURNING plan, window_start, window_end, searches_used, newsletters_sent;
                        """,
                        (user_id, limit),
                    )
                    updated = cur.fetchone()

            if not updated:
                # Limit reached (or retry still failed)
                # preserve your behavior: pro reverts to free when limit ends/over
                if pw["plan"] == "pro":
                    reset_window(user_id, "free")
                raise HTTPException(status_code=402, detail=f"search limit reached ({limit}/24h). Upgrade required.")

            # Only log if we actually consumed a search
            cur.execute(
                """
                INSERT INTO user_search_log (user_id, mode, ticker, start_date, end_date, performance, quantity)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
                """,
                (user_id, mode, ticker, start_date, end_date, performance, quantity),
            )

        conn.commit()

    plan, window_start, window_end, used, newsletters_sent = updated
    return {
        "plan": plan,
        "window_start": window_start,
        "window_end": window_end,
        "searches_used": int(used),
        "newsletters_sent": int(newsletters_sent or 0),
        "limit": PRO_LIMIT if plan == "pro" else FREE_LIMIT,
        "newsletter_limit": PRO_NEWSLETTER_LIMIT,
    }