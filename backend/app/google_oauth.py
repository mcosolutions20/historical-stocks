from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import HTTPException

from google.oauth2 import id_token
from google.auth.transport import requests


def verify_google_id_token(token: str) -> Dict[str, Any]:
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    if not client_id:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID not set on backend")

    try:
        info = id_token.verify_oauth2_token(token, requests.Request(), client_id)
    except Exception:
        raise HTTPException(status_code=401, detail="invalid google token")

    # defensive checks
    if info.get("aud") != client_id:
        raise HTTPException(status_code=401, detail="google token aud mismatch")
    if not info.get("email"):
        raise HTTPException(status_code=401, detail="google token missing email")

    return info