# backend/app/auth.py
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from fastapi import HTTPException, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr

from .db import get_conn
from .emailer import send_verification_email


JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-me")
JWT_ALG = "HS256"
JWT_EXPIRE_MIN = int(os.getenv("JWT_EXPIRE_MIN", "120"))

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)


class RegisterBody(BaseModel):
    email: EmailStr
    username: str
    password: str


class LoginBody(BaseModel):
    username_or_email: str
    password: str


class ResendVerifyBody(BaseModel):
    email: EmailStr


def init_auth_tables() -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS app_users (
      id BIGSERIAL PRIMARY KEY,
      email TEXT UNIQUE NOT NULL,
      username TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      is_verified BOOLEAN NOT NULL DEFAULT FALSE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS email_verification_tokens (
      token TEXT PRIMARY KEY,
      user_id BIGINT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
      expires_at TIMESTAMPTZ NOT NULL,
      used_at TIMESTAMPTZ NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS user_plan_windows (
        user_id BIGINT PRIMARY KEY REFERENCES app_users(id) ON DELETE CASCADE,
        plan TEXT NOT NULL DEFAULT 'free',
        window_start TIMESTAMPTZ NOT NULL,
        window_end TIMESTAMPTZ NOT NULL,
        searches_used INT NOT NULL DEFAULT 0,
        newsletters_sent INT NOT NULL DEFAULT 0,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    ALTER TABLE user_plan_windows
      ADD COLUMN IF NOT EXISTS newsletters_sent INT NOT NULL DEFAULT 0;
    ALTER TABLE user_plan_windows
      ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

    CREATE TABLE IF NOT EXISTS user_search_log (
      id BIGSERIAL PRIMARY KEY,
      user_id BIGINT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
      searched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      mode TEXT NOT NULL,
      ticker TEXT NULL,
      start_date DATE NOT NULL,
      end_date DATE NOT NULL,
      performance TEXT NULL,
      quantity INT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_user_search_log_user_time
      ON user_search_log(user_id, searched_at DESC);

    -- =========================
    -- Portfolio CRUD
    -- =========================
    CREATE TABLE IF NOT EXISTS portfolios (
      id BIGSERIAL PRIMARY KEY,
      user_id BIGINT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
      name TEXT NOT NULL,
      cash_balance NUMERIC(18, 2) NOT NULL DEFAULT 0,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT uniq_portfolio_name_per_user UNIQUE (user_id, name)
    );

    -- migrate older DBs
    ALTER TABLE portfolios
      ADD COLUMN IF NOT EXISTS cash_balance NUMERIC(18, 2) NOT NULL DEFAULT 0;

    CREATE INDEX IF NOT EXISTS idx_portfolios_user
      ON portfolios(user_id);

    CREATE TABLE IF NOT EXISTS holdings (
      id BIGSERIAL PRIMARY KEY,
      portfolio_id BIGINT NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
      ticker TEXT NOT NULL,
      shares NUMERIC(18, 6) NOT NULL,
      avg_cost NUMERIC(18, 4) NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT uniq_holding_per_portfolio UNIQUE (portfolio_id, ticker)
    );

    CREATE INDEX IF NOT EXISTS idx_holdings_portfolio
      ON holdings(portfolio_id);
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_password(pw: str) -> str:
    if len(pw.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="password too long (max 72 bytes)")
    return pwd_ctx.hash(pw)


def _verify_password(pw: str, hashed: str) -> bool:
    if hashed == "GOOGLE_OAUTH":
        return False
    return pwd_ctx.verify(pw, hashed)


def _make_jwt(user_id: int, username: str) -> str:
    now = _utcnow()
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=JWT_EXPIRE_MIN)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def _decode_jwt(token: str) -> Dict[str, Any]:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])


def _create_24h_window(user_id: int, plan: str) -> None:
    now = _utcnow()
    window_end = now + timedelta(hours=24)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_plan_windows (user_id, plan, window_start, window_end, searches_used)
                VALUES (%s, %s, %s, %s, 0)
                ON CONFLICT (user_id) DO UPDATE SET
                  plan = EXCLUDED.plan,
                  window_start = EXCLUDED.window_start,
                  window_end = EXCLUDED.window_end,
                  searches_used = 0,
                  updated_at = NOW();
                """,
                (user_id, plan, now, window_end),
            )
        conn.commit()


def _create_verification_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = _utcnow() + timedelta(hours=24)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO email_verification_tokens (token, user_id, expires_at)
                VALUES (%s, %s, %s)
                """,
                (token, user_id, expires),
            )
        conn.commit()
    return token


def _issue_and_email_verification(user_id: int, email: str) -> None:
    token = _create_verification_token(user_id)
    send_verification_email(email, token)


def register_user(email: str, username: str, password: str) -> Dict[str, Any]:
    email = email.strip().lower()
    username = username.strip()

    if len(username) < 3:
        raise HTTPException(status_code=400, detail="username must be at least 3 characters")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="password must be at least 8 characters")

    pw_hash = _hash_password(password)

    with get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO app_users (email, username, password_hash)
                    VALUES (%s, %s, %s)
                    RETURNING id;
                    """,
                    (email, username, pw_hash),
                )
                user_id = cur.fetchone()[0]
            except Exception:
                conn.rollback()
                raise HTTPException(status_code=400, detail="email or username already exists")
        conn.commit()

    _create_24h_window(user_id=int(user_id), plan="free")
    _issue_and_email_verification(int(user_id), email)

    return {"message": "Account created. Check your email to verify."}


def login_user(username_or_email: str, password: str) -> Dict[str, Any]:
    key = username_or_email.strip()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, username, password_hash, is_verified
                FROM app_users
                WHERE username = %s OR email = %s
                LIMIT 1;
                """,
                (key, key.lower()),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="invalid credentials")

    user_id, username, pw_hash, is_verified = row

    if not _verify_password(password, pw_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")

    token = _make_jwt(user_id=int(user_id), username=username)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": int(user_id), "username": username, "is_verified": bool(is_verified)},
    }


def resend_verification(email: str) -> Dict[str, Any]:
    email = email.strip().lower()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, is_verified FROM app_users WHERE email=%s LIMIT 1;", (email,))
            row = cur.fetchone()

    if not row:
        return {"message": "If that account exists, an email was sent."}

    user_id, is_verified = row
    if is_verified:
        return {"message": "Email is already verified."}

    _issue_and_email_verification(int(user_id), email)
    return {"message": "Verification email sent."}


def verify_email(token: str) -> Dict[str, Any]:
    now = _utcnow()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, expires_at, used_at
                FROM email_verification_tokens
                WHERE token = %s
                LIMIT 1;
                """,
                (token,),
            )
            row = cur.fetchone()

            if not row:
                raise HTTPException(status_code=400, detail="invalid token")

            user_id, expires_at, used_at = row

            if used_at is not None:
                raise HTTPException(status_code=400, detail="token already used")

            if expires_at is None or expires_at < now:
                raise HTTPException(status_code=400, detail="token expired")

            cur.execute("UPDATE app_users SET is_verified = TRUE WHERE id = %s;", (user_id,))
            cur.execute("UPDATE email_verification_tokens SET used_at = NOW() WHERE token = %s;", (token,))
        conn.commit()

    return {"message": "Email verified. You can now use secure endpoints."}


def get_current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> Dict[str, Any]:
    if creds is None:
        raise HTTPException(status_code=401, detail="missing Authorization header")

    token = creds.credentials
    try:
        payload = _decode_jwt(token)
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="invalid token")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, email, is_verified FROM app_users WHERE id = %s LIMIT 1;",
                (user_id,),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="user not found")

    uid, username, email, is_verified = row
    return {"id": int(uid), "username": username, "email": email, "is_verified": bool(is_verified)}
