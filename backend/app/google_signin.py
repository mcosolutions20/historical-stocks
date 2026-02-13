# backend/app/google_signin.py
from __future__ import annotations

import os
from typing import Dict, Any

from fastapi import HTTPException
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from .db import get_conn


def verify_google_id_token(token: str) -> Dict[str, Any]:
    """
    Verify a Google ID token against GOOGLE_CLIENT_ID.

    Dev note:
      On Windows + Docker Desktop you can get tiny clock skew.
      We allow a small skew ONLY in dev.
    """
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    if not client_id:
        raise HTTPException(
            status_code=500,
            detail={"code": "google_not_configured", "message": "GOOGLE_CLIENT_ID not set on backend"},
        )

    if not token or not isinstance(token, str):
        raise HTTPException(
            status_code=400,
            detail={"code": "google_token_missing", "message": "Missing Google credential"},
        )

    # Allow a small skew in development to avoid local Docker clock drift issues
    env = os.getenv("ENV", "dev").lower().strip()
    skew = int(os.getenv("GOOGLE_CLOCK_SKEW_SECONDS", "5")) if env != "prod" else 0

    try:
        info = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            client_id,
            clock_skew_in_seconds=skew,
        )
    except Exception as e:
        print(f"[google] token verify failed: {repr(e)}")
        raise HTTPException(
            status_code=401,
            detail={"code": "google_token_invalid", "message": "Invalid Google token"},
        )

    aud = info.get("aud")
    if aud != client_id:
        raise HTTPException(
            status_code=401,
            detail={"code": "google_aud_mismatch", "message": "Google token audience mismatch"},
        )

    email = info.get("email")
    if not email:
        raise HTTPException(
            status_code=401,
            detail={"code": "google_email_missing", "message": "Google token missing email"},
        )

    return info


def get_or_create_google_user(email: str, username_seed: str) -> Dict[str, Any]:
    """
    Production-style: Google users are considered verified immediately.
    """
    email = email.strip().lower()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, is_verified FROM app_users WHERE email=%s LIMIT 1;",
                (email,),
            )
            row = cur.fetchone()

            if row:
                uid, username, is_verified = row
                if not bool(is_verified):
                    cur.execute("UPDATE app_users SET is_verified=TRUE WHERE id=%s;", (uid,))
                    conn.commit()
                    is_verified = True
                return {"id": int(uid), "username": username, "is_verified": bool(is_verified)}

            base = (username_seed or "user").strip().lower().replace(" ", "")
            if len(base) < 3:
                base = "user"
            base = base[:24]

            username = base
            suffix = 0
            while True:
                cur.execute("SELECT 1 FROM app_users WHERE username=%s LIMIT 1;", (username,))
                if not cur.fetchone():
                    break
                suffix += 1
                username = f"{base}{suffix}"[:30]

            cur.execute(
                """
                INSERT INTO app_users (email, username, password_hash, is_verified)
                VALUES (%s, %s, %s, TRUE)
                RETURNING id;
                """,
                (email, username, "GOOGLE_OAUTH"),
            )
            user_id = int(cur.fetchone()[0])
            conn.commit()

    from .usage import reset_window
    reset_window(int(user_id), "free")

    return {"id": int(user_id), "username": username, "is_verified": True}