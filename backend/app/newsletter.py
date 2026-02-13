# backend/app/newsletter.py
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta, date
from typing import List, Dict, Any, Tuple, Optional

import requests
from fastapi import HTTPException

from .db import get_conn
from .portfolios import get_portfolio_valuation, get_portfolio_performance


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_window_and_searches(user_id: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT plan, window_start, window_end, searches_used
                FROM user_plan_windows
                WHERE user_id=%s
                LIMIT 1;
                """,
                (user_id,),
            )
            pw = cur.fetchone()

            if not pw:
                raise HTTPException(status_code=400, detail="No plan window found for user.")

            plan, ws, we, used = pw

            cur.execute(
                """
                SELECT searched_at, mode, ticker, start_date, end_date, performance, quantity
                FROM user_search_log
                WHERE user_id=%s
                  AND searched_at >= %s
                  AND searched_at <= %s
                ORDER BY searched_at DESC
                LIMIT 200;
                """,
                (user_id, ws, we),
            )
            rows = cur.fetchall()

    searches = []
    for r in rows:
        searched_at, mode, ticker, start_date, end_date, performance, quantity = r
        searches.append(
            {
                "searched_at": searched_at.isoformat(),
                "mode": mode,
                "ticker": ticker,
                "start_date": str(start_date),
                "end_date": str(end_date),
                "performance": performance,
                "quantity": int(quantity) if quantity is not None else None,
            }
        )

    window = {
        "plan": plan,
        "window_start": ws.isoformat() if ws else None,
        "window_end": we.isoformat() if we else None,
        "searches_used": int(used),
    }

    return window, searches


def _load_portfolio_context(user_id: int) -> Dict[str, Any]:
    """
    Personalization from the user's most recent portfolio:
    - current valuation (cash + positions)
    - top holdings
    - recent performance vs SP500 (last 30 days, if possible)
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, cash_balance, updated_at
                FROM portfolios
                WHERE user_id = %s
                ORDER BY updated_at DESC
                LIMIT 1;
                """,
                (user_id,),
            )
            p = cur.fetchone()

            if not p:
                return {"has_portfolio": False}

            portfolio_id, name, cash_balance, updated_at = p

            # Latest benchmark date (used for selecting a reasonable performance window)
            cur.execute("SELECT MAX(trade_date) FROM sp500_index_daily;")
            max_day = cur.fetchone()[0]

    ctx: Dict[str, Any] = {
        "has_portfolio": True,
        "portfolio_id": int(portfolio_id),
        "portfolio_name": name,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }

    # Current valuation / holdings (derived from transactions)
    try:
        val = get_portfolio_valuation(user_id=user_id, portfolio_id=int(portfolio_id))
        ctx["valuation"] = val.get("totals", {})
        # keep it short: top 10 holdings by market value
        positions = sorted(val.get("positions", []), key=lambda x: float(x.get("market_value") or 0), reverse=True)
        ctx["top_holdings"] = [
            {
                "ticker": p.get("ticker"),
                "shares": p.get("shares"),
                "market_value": p.get("market_value"),
                "avg_cost": p.get("avg_cost"),
                "last_price": p.get("last_price"),
            }
            for p in positions[:10]
        ]
    except Exception:
        ctx["valuation"] = None
        ctx["top_holdings"] = []

    # Recent performance vs SP500 (last ~30 days)
    try:
        if max_day:
            end = max_day
            start = max_day - timedelta(days=30)
            perf = get_portfolio_performance(user_id=user_id, portfolio_id=int(portfolio_id), start=start, end=end, benchmark_ticker="SP500")
            ctx["performance_30d"] = perf.get("metrics")
    except Exception:
        ctx["performance_30d"] = None

    return ctx

def _build_prompt(email: str, window: Dict[str, Any], searches: List[Dict[str, Any]], portfolio_ctx: Dict[str, Any]) -> str:
    tickers = [s["ticker"] for s in searches if s.get("ticker")]
    unique_tickers = sorted({t.upper() for t in tickers})[:25]

    modes: Dict[str, int] = {}
    for s in searches:
        m = s.get("mode") or "unknown"
        modes[m] = modes.get(m, 0) + 1

    lines: List[str] = []
    lines.append("You are generating a personalized daily market newsletter for a demo portfolio app.")
    lines.append("Rules:")
    lines.append("- Do NOT give financial advice. Do NOT tell the user to buy/sell/hold.")
    lines.append("- Keep it practical: explain concepts, summarize themes, provide neutral watch-items.")
    lines.append("- Be concise and structured with headings and bullet points.")
    lines.append("")
    lines.append(f"User email: {email}")
    lines.append(f"Current plan window: {window}")
    lines.append("")
    lines.append("Recent user activity (searches in this window):")
    lines.append(f"- Unique tickers searched: {unique_tickers}")
    lines.append(f"- Search modes counts: {modes}")
    lines.append("- Latest searches (most recent first):")
    for s in searches[:25]:
        lines.append(
            f"  - {s['searched_at']} | mode={s.get('mode')} | ticker={s.get('ticker')} | "
            f"{s.get('start_date')}→{s.get('end_date')} | perf={s.get('performance')} | qty={s.get('quantity')}"
        )

    lines.append("")
    lines.append("Portfolio context (for personalization only):")
    if not portfolio_ctx.get("has_portfolio"):
        lines.append("- No portfolio data available for this user.")
    else:
        lines.append(f"- Portfolio: {portfolio_ctx.get('portfolio_name')} (id={portfolio_ctx.get('portfolio_id')})")

        val = portfolio_ctx.get("valuation") or {}
        # your valuation dict has totals like cash_current/total_value etc
        if isinstance(val, dict) and val:
            lines.append(f"- Totals: {val}")

        top = portfolio_ctx.get("top_holdings") or []
        if top:
            lines.append("- Top holdings (ticker, shares, market_value, avg_cost, last_price):")
            for h in top[:10]:
                lines.append(
                    f"  - {h.get('ticker')}: shares={h.get('shares')} "
                    f"mv={h.get('market_value')} avg_cost={h.get('avg_cost')} last_price={h.get('last_price')}"
                )
        else:
            lines.append("- Holdings: none (add transactions to create holdings)")

        perf = portfolio_ctx.get("performance_30d")
        if perf is not None:
            lines.append(f"- Recent performance (approx 30d): {perf}")

    lines.append("")
    lines.append("Output format:")
    lines.append("1) 'Today’s focus' (2-4 bullets, neutral)")
    lines.append("2) 'Portfolio spotlight' (mention tickers from holdings; if none, explain how to add holdings)")
    lines.append("3) 'Based on your searches' (mention tickers searched and what metrics to watch)")
    lines.append("4) 'Education bite' (1 short concept: drawdown, volatility, Sharpe, diversification, etc.)")
    lines.append("5) 'Next actions in the app' (2-3 bullets describing features the user can click in the app)")
    return "\n".join(lines)


def _call_openai(prompt: str) -> str:
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set")

    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "input": prompt,
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=45)
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"OpenAI request failed: {str(e)}")

    # Responses API can return text in different places; handle common shapes safely.
    # Preferred: output_text if present.
    if "output_text" in data and isinstance(data["output_text"], str):
        return data["output_text"].strip()

    # Fallback: walk output -> content -> text
    try:
        out = data.get("output", [])
        parts = []
        for item in out:
            for c in item.get("content", []):
                if c.get("type") == "output_text" and "text" in c:
                    parts.append(c["text"])
        txt = "\n".join(parts).strip()
        if txt:
            return txt
    except Exception:
        pass

    raise HTTPException(status_code=502, detail="OpenAI response missing text output")


def generate_newsletter(user_id: int, email: str) -> Dict[str, Any]:
    window, searches = _load_window_and_searches(user_id)
    portfolio_ctx = _load_portfolio_context(user_id)
    prompt = _build_prompt(email=email, window=window, searches=searches, portfolio_ctx=portfolio_ctx)

    text = _call_openai(prompt)
    return {"newsletter": text, "generated_at": _utcnow().isoformat()}
