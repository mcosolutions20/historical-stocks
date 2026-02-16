import os
from dotenv import load_dotenv

load_dotenv()

from datetime import date
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Depends, Request, UploadFile, File, Query
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .queries import get_single_stock, get_outliers, get_meta
from .auth import (
    init_auth_tables,
    RegisterBody,
    LoginBody,
    ResendVerifyBody,
    register_user,
    login_user,
    verify_email,
    resend_verification,
    get_current_user,
)
from .usage import (
    enforce_and_increment,
    get_plan_window,
    consume_newsletter_generation,
)
from .google_signin import verify_google_id_token, get_or_create_google_user
from .auth import _make_jwt
from .stripe_billing import create_checkout_session, handle_stripe_webhook
from .newsletter import generate_newsletter
from .emailer import send_newsletter_email

from .portfolios import (
    init_portfolio_tables,
    list_portfolios,
    create_portfolio,
    update_portfolio,
    delete_portfolio,
    get_portfolio_detail,
    get_portfolio_valuation,
    get_portfolio_performance,
    rebalance_suggestion,
    list_transactions,
    create_transaction,
    update_transaction,
    delete_transaction,    export_transactions_csv,
    import_transactions_csv,
    export_performance_csv,
)

STOCK_CACHE_TTL_SECONDS = int(os.getenv("STOCK_CACHE_TTL_SECONDS", "120"))
OUTLIERS_CACHE_TTL_SECONDS = int(os.getenv("OUTLIERS_CACHE_TTL_SECONDS", "120"))
META_CACHE_TTL_SECONDS = int(os.getenv("META_CACHE_TTL_SECONDS", "300"))

app = FastAPI(title="Historical Stocks API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    init_auth_tables()
    init_portfolio_tables()


@app.get("/meta")
def meta():
    from .cache import cache_get, cache_set

    key = "meta:v1"
    cached = cache_get(key)
    if cached is not None:
        return cached

    out = get_meta()
    cache_set(key, out, ttl_seconds=META_CACHE_TTL_SECONDS)
    return out


@app.get("/health")
def health():
    return {"status": "ok"}


# =========================
# Auth routes
# =========================
@app.post("/auth/register")
def auth_register(body: RegisterBody):
    return register_user(body.email, body.username, body.password)


@app.post("/auth/login")
def auth_login(body: LoginBody):
    return login_user(body.username_or_email, body.password)


@app.post("/auth/resend-verification")
def auth_resend(body: ResendVerifyBody):
    return resend_verification(body.email)


@app.get("/auth/verify/{token}")
def auth_verify(token: str):
    return verify_email(token)


class GoogleBody(BaseModel):
    id_token: str


from pydantic import BaseModel

class GoogleAuthBody(BaseModel):
    credential: str  # the Google ID token


@app.post("/auth/google")
def auth_google(body: GoogleBody):
    info = verify_google_id_token(body.id_token)
    email = (info.get("email") or "").lower().strip()
    name = (info.get("name") or "googleuser").strip()

    if not email:
        raise HTTPException(status_code=400, detail={"code": "google_email_missing", "message": "Missing email"})

    user = get_or_create_google_user(email=email, username_seed=name)

    # At this point Google users are always verified
    token = _make_jwt(user_id=user["id"], username=user["username"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user["id"], "username": user["username"], "is_verified": True},
        "message": "Signed in with Google.",
    }


@app.get("/me")
def me(user=Depends(get_current_user)):
    pw = get_plan_window(user["id"])
    return {"user": user, "plan_window": pw}


# =========================
# Stripe billing
# =========================
@app.post("/billing/create-checkout-session")
def billing_create_checkout(user=Depends(get_current_user)):
    """
    Production:
      - If Stripe configured: return {url} for Checkout.
    Dev:
      - If Stripe NOT configured and DEV_BILLING_BYPASS=true: immediately upgrade to Pro for 24h.
    """
    if not user["is_verified"]:
        raise HTTPException(status_code=403, detail="email not verified")

    import os
    from .stripe_billing import stripe_is_configured, upgrade_user_to_pro_24h

    dev_bypass = (os.getenv("DEV_BILLING_BYPASS", "false").lower().strip() == "true")

    if (not stripe_is_configured()) and dev_bypass:
        upgrade_user_to_pro_24h(user["id"])
        return {"url": None, "dev_upgraded": True}

    return create_checkout_session(user_id=user["id"], user_email=user["email"])


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    return await handle_stripe_webhook(request)


# =========================
# Newsletter
# =========================
class SendNewsletterBody(BaseModel):
    newsletter: str


@app.get("/newsletter/preview")
def newsletter_preview(user=Depends(get_current_user)):
    usage = consume_newsletter_generation(user_id=user["id"], is_verified=user["is_verified"])
    payload = generate_newsletter(user_id=user["id"], email=user["email"])
    return {
        "newsletter": payload.get("newsletter", ""),
        "remaining": usage["remaining"],
        "window_end": usage["window_end"],
    }


@app.post("/newsletter/send")
def newsletter_send(body: SendNewsletterBody, user=Depends(get_current_user)):
    if not user["is_verified"]:
        raise HTTPException(status_code=403, detail="email not verified")

    pw = get_plan_window(user["id"])
    if pw["plan"] != "pro":
        raise HTTPException(status_code=403, detail="Newsletter is available for Pro users only.")

    text = (body.newsletter or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="newsletter text is required")

    send_newsletter_email(user["email"], text)
    return {"sent": True}


# =========================
# Portfolio CRUD
# =========================
class PortfolioCreateBody(BaseModel):
    name: str
    cash_balance: Optional[float] = 0


class PortfolioUpdateBody(BaseModel):
    name: Optional[str] = None
    cash_balance: Optional[float] = None


class RebalanceTarget(BaseModel):
    ticker: str
    weight: float


class RebalanceBody(BaseModel):
    targets: List[RebalanceTarget]
    include_cash_in_total: bool = True


class TxCreateBody(BaseModel):
    ticker: str
    side: str
    shares: float
    price: Optional[float] = None
    trade_date: date
    notes: Optional[str] = None


class TxUpdateBody(BaseModel):
    side: str
    shares: float
    price: Optional[float] = None
    trade_date: date
    notes: Optional[str] = None


@app.get("/portfolios")
def portfolios_list(user=Depends(get_current_user)):
    if not user["is_verified"]:
        raise HTTPException(status_code=403, detail="email not verified")
    return {"portfolios": list_portfolios(user["id"])}


@app.post("/portfolios")
def portfolios_create(body: PortfolioCreateBody, user=Depends(get_current_user)):
    if not user["is_verified"]:
        raise HTTPException(status_code=403, detail="email not verified")
    return {"portfolio": create_portfolio(user["id"], body.name, body.cash_balance or 0)}


@app.get("/portfolios/{portfolio_id}")
def portfolios_detail(portfolio_id: int, user=Depends(get_current_user)):
    if not user["is_verified"]:
        raise HTTPException(status_code=403, detail="email not verified")
    return get_portfolio_detail(user["id"], portfolio_id)


@app.put("/portfolios/{portfolio_id}")
def portfolios_update(portfolio_id: int, body: PortfolioUpdateBody, user=Depends(get_current_user)):
    if not user["is_verified"]:
        raise HTTPException(status_code=403, detail="email not verified")
    return {"portfolio": update_portfolio(user["id"], portfolio_id, body.name, body.cash_balance)}


@app.delete("/portfolios/{portfolio_id}")
def portfolios_delete(portfolio_id: int, user=Depends(get_current_user)):
    if not user["is_verified"]:
        raise HTTPException(status_code=403, detail="email not verified")
    return delete_portfolio(user["id"], portfolio_id)


@app.get("/portfolios/{portfolio_id}/valuation")
def portfolios_valuation(portfolio_id: int, user=Depends(get_current_user)):
    if not user["is_verified"]:
        raise HTTPException(status_code=403, detail="email not verified")
    return get_portfolio_valuation(user["id"], portfolio_id)


@app.get("/portfolios/{portfolio_id}/performance")
def portfolios_performance(
    portfolio_id: int,
    start: date = Query(...),
    end: date = Query(...),
    benchmark: str = Query("SP500"),
    user=Depends(get_current_user),
):
    if not user["is_verified"]:
        raise HTTPException(status_code=403, detail="email not verified")
    return get_portfolio_performance(user["id"], portfolio_id, start=start, end=end, benchmark_ticker=benchmark)

# ]]]]
@app.get("/portfolios/{portfolio_id}/performance/export")
def portfolios_performance_export(
    portfolio_id: int,
    start: date = Query(...),
    end: date = Query(...),
    benchmark: str = Query("SP500"),
    user=Depends(get_current_user),
):
    if not user["is_verified"]:
        raise HTTPException(status_code=403, detail="email not verified")

    out = export_performance_csv(
        user_id=user["id"],
        portfolio_id=portfolio_id,
        start=start,
        end=end,
        benchmark_ticker=benchmark,
    )

    filename = out.get("filename") or f"portfolio_{portfolio_id}_performance.csv"
    csv_text = out.get("csv") or ""

    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
# ]]]]]


@app.post("/portfolios/{portfolio_id}/rebalance")
def portfolios_rebalance(portfolio_id: int, body: RebalanceBody, user=Depends(get_current_user)):
    if not user["is_verified"]:
        raise HTTPException(status_code=403, detail="email not verified")
    targets = [{"ticker": t.ticker, "weight": t.weight} for t in body.targets]
    return rebalance_suggestion(user["id"], portfolio_id, targets=targets, include_cash_in_total=body.include_cash_in_total)


# =========================
# Transactions endpoints
# =========================
@app.get("/portfolios/{portfolio_id}/transactions")
def transactions_list(portfolio_id: int, user=Depends(get_current_user)):
    if not user["is_verified"]:
        raise HTTPException(status_code=403, detail="email not verified")
    return list_transactions(user["id"], portfolio_id)


@app.post("/portfolios/{portfolio_id}/transactions")
def transactions_create(portfolio_id: int, body: TxCreateBody, user=Depends(get_current_user)):
    if not user["is_verified"]:
        raise HTTPException(status_code=403, detail="email not verified")
    tx = create_transaction(
        user_id=user["id"],
        portfolio_id=portfolio_id,
        ticker=body.ticker,
        side=body.side,
        shares=body.shares,
        price=body.price,
        trade_date=body.trade_date,
        notes=body.notes,
    )
    return {"transaction": tx}


@app.put("/transactions/{transaction_id}")
def transactions_update(transaction_id: int, body: TxUpdateBody, user=Depends(get_current_user)):
    if not user["is_verified"]:
        raise HTTPException(status_code=403, detail="email not verified")
    tx = update_transaction(
        user_id=user["id"],
        transaction_id=transaction_id,
        side=body.side,
        shares=body.shares,
        price=body.price,
        trade_date=body.trade_date,
        notes=body.notes,
    )
    return {"transaction": tx}


@app.delete("/transactions/{transaction_id}")
def transactions_delete(transaction_id: int, user=Depends(get_current_user)):
    if not user["is_verified"]:
        raise HTTPException(status_code=403, detail="email not verified")
    return delete_transaction(user["id"], transaction_id)


@app.get("/portfolios/{portfolio_id}/transactions/export")
def transactions_export(portfolio_id: int, user=Depends(get_current_user)):
    if not user["is_verified"]:
        raise HTTPException(status_code=403, detail="email not verified")
    out = export_transactions_csv(user["id"], portfolio_id)
    # Return as a downloadable CSV file
    return Response(
        content=out["csv"],
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{out["filename"]}"'},
    )


@app.post("/portfolios/{portfolio_id}/transactions/import")
async def transactions_import(portfolio_id: int, file: UploadFile = File(...), user=Depends(get_current_user)):
    if not user["is_verified"]:
        raise HTTPException(status_code=403, detail="email not verified")
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")
    csv_text = (await file.read()).decode("utf-8", errors="replace")
    return import_transactions_csv(user["id"], portfolio_id, csv_text)

# =========================
# Existing public endpoints
# =========================
@app.get("/stock/{start}/{end}/{ticker}")
def stock(start: date, end: date, ticker: str):
    from .cache import cache_get, cache_set

    t = ticker.upper().strip()
    key = f"pub:stock:v2:t={t}:start={start.isoformat()}:end={end.isoformat()}"

    cached = cache_get(key)
    if cached is not None:
        return cached

    result = get_single_stock(t, start, end)
    out = [result] if result else []

    cache_set(key, out, ttl_seconds=STOCK_CACHE_TTL_SECONDS)
    return out


@app.get("/outlier/{start}/{end}/{performance}/{quantity}")
def outlier(start: date, end: date, performance: str, quantity: int):
    from .cache import cache_get, cache_set

    perf = performance.lower().strip()
    if perf not in ("top", "bottom"):
        raise HTTPException(status_code=400, detail="performance must be 'top' or 'bottom'")

    n = max(1, min(quantity, 500))

    key = f"pub:outlier:v2:perf={perf}:start={start.isoformat()}:end={end.isoformat()}:n={n}"
    cached = cache_get(key)
    if cached is not None:
        return cached

    out = get_outliers(start, end, perf, n)
    cache_set(key, out, ttl_seconds=OUTLIERS_CACHE_TTL_SECONDS)
    return out


# =========================
# Secured endpoints
# =========================
@app.get("/secure/stock/{start}/{end}/{ticker}")
def secure_stock(start: date, end: date, ticker: str, user=Depends(get_current_user)):
    from .cache import cache_get, cache_set

    t = ticker.upper().strip()

    # 1) Always enforce/increment usage (DO NOT cache this)
    usage = enforce_and_increment(
        user_id=user["id"],
        is_verified=user["is_verified"],
        mode="stock",
        start_date=start,
        end_date=end,
        ticker=t,
    )

    # 2) Cache ONLY the heavy data (safe because it doesn't depend on user)
    key = f"sec:data:stock:v2:t={t}:start={start.isoformat()}:end={end.isoformat()}"
    data = cache_get(key)
    if data is None:
        result = get_single_stock(t, start, end)
        data = [result] if result else []
        cache_set(key, data, ttl_seconds=STOCK_CACHE_TTL_SECONDS)

    return {"usage": usage, "data": data}


@app.get("/secure/outlier/{start}/{end}/{performance}/{quantity}")
def secure_outlier(start: date, end: date, performance: str, quantity: int, user=Depends(get_current_user)):
    from .cache import cache_get, cache_set

    perf = performance.lower().strip()
    if perf not in ("top", "bottom"):
        raise HTTPException(status_code=400, detail="performance must be 'top' or 'bottom'")

    n = max(1, min(quantity, 500))

    # 1) Always enforce/increment usage (DO NOT cache this)
    usage = enforce_and_increment(
        user_id=user["id"],
        is_verified=user["is_verified"],
        mode=perf,
        start_date=start,
        end_date=end,
        performance=perf,
        quantity=n,
    )

    # 2) Cache ONLY the heavy data
    key = f"sec:data:outlier:v2:perf={perf}:start={start.isoformat()}:end={end.isoformat()}:n={n}"
    data = cache_get(key)
    if data is None:
        data = get_outliers(start, end, perf, n)
        cache_set(key, data, ttl_seconds=OUTLIERS_CACHE_TTL_SECONDS)

    return {"usage": usage, "data": data}


