from __future__ import annotations

import os
import stripe
from fastapi import HTTPException, Request

from .usage import reset_window

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")


def stripe_is_configured() -> bool:
    return bool(STRIPE_SECRET_KEY and STRIPE_PRICE_ID)


def _require_config():
    missing = []
    if not STRIPE_SECRET_KEY:
        missing.append("STRIPE_SECRET_KEY")
    if not STRIPE_PRICE_ID:
        missing.append("STRIPE_PRICE_ID")

    if missing:
        # Clear, non-500 response when Stripe isn't set up yet
        raise HTTPException(
            status_code=501,
            detail={
                "code": "billing_not_configured",
                "message": f"Stripe not configured: {', '.join(missing)}",
                "missing": missing,
            },
        )

    stripe.api_key = STRIPE_SECRET_KEY


def upgrade_user_to_pro_24h(user_id: int) -> None:
    reset_window(user_id, "pro")


def create_checkout_session(*, user_id: int, user_email: str) -> dict:
    _require_config()

    success_url = f"{FRONTEND_BASE_URL}/?checkout=success"
    cancel_url = f"{FRONTEND_BASE_URL}/?checkout=cancel"

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            client_reference_id=str(user_id),
            customer_email=user_email,
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"user_id": str(user_id)},
        )
        return {"url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stripe session error: {str(e)}")


async def handle_stripe_webhook(request: Request) -> dict:
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=501,
            detail={"code": "webhook_not_configured", "message": "Stripe webhook not configured (STRIPE_WEBHOOK_SECRET)"},
        )

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid webhook signature: {str(e)}")

    event_type = event["type"]

    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        ref = session.get("client_reference_id") or session.get("metadata", {}).get("user_id")

        if not ref:
            return {"received": True, "type": event_type, "upgraded": False, "reason": "missing user ref"}

        user_id = int(ref)
        upgrade_user_to_pro_24h(user_id)
        return {"received": True, "type": event_type, "upgraded": True, "user_id": user_id}

    return {"received": True, "type": event_type}