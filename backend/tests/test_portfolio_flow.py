from datetime import date


def _auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"


def test_portfolio_transaction_and_performance(client, db_seed):
    headers = _auth_headers(db_seed["token"])

    # Create portfolio
    resp = client.post(
        "/portfolios",
        json={"name": "My Test Portfolio", "cash_balance": 10_000},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    portfolio = resp.json()["portfolio"]
    pid = int(portfolio["id"])

    # BUY 10 AAPL @ 50 on 2024-01-02
    resp = client.post(
        f"/portfolios/{pid}/transactions",
        json={
            "ticker": "AAPL",
            "side": "BUY",
            "shares": 10,
            "price": 50,
            "trade_date": date(2024, 1, 2).isoformat(),
            "notes": "seed",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    # Prevent negative shares (attempt to SELL more than owned)
    resp = client.post(
        f"/portfolios/{pid}/transactions",
        json={
            "ticker": "AAPL",
            "side": "SELL",
            "shares": 20,
            "price": 51,
            "trade_date": date(2024, 1, 3).isoformat(),
        },
        headers=headers,
    )
    assert resp.status_code == 400

    # Performance should compute over seeded window
    resp = client.get(
        f"/portfolios/{pid}/performance",
        params={"start": "2024-01-02", "end": "2024-01-04", "benchmark": "SP500"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["portfolio_id"] == pid
    assert data["start"] == "2024-01-02"
    assert data["end"] == "2024-01-04"
    assert len(data["series"]) == 3

    # Portfolio should gain value as AAPL price rises.
    total_return = data["metrics"]["portfolio"]["total_return"]
    assert total_return is not None
    assert total_return > 0