def _hit_secure_outlier(client, headers):
    # Keep within your seeded dates in conftest.py
    return client.get("/secure/outlier/2024-01-02/2024-01-04/top/1", headers=headers)


def test_free_limit_enforced_5_per_24h(client, auth_headers, db_seed):
    # First 5 should pass
    for _ in range(5):
        r = _hit_secure_outlier(client, auth_headers)
        assert r.status_code == 200, r.text

    # 6th should block
    r6 = _hit_secure_outlier(client, auth_headers)
    assert r6.status_code == 402, r6.text


def test_dev_bypass_upgrade_turns_user_pro(client, auth_headers, db_seed):
    # Exhaust free limit
    for _ in range(5):
        r = _hit_secure_outlier(client, auth_headers)
        assert r.status_code == 200, r.text

    # Confirm blocked now
    blocked = _hit_secure_outlier(client, auth_headers)
    assert blocked.status_code == 402, blocked.text

    # Call billing (Stripe bypass)
    b = client.post("/billing/create-checkout-session", headers=auth_headers)
    assert b.status_code == 200, b.text
    data = b.json()
    assert data.get("dev_upgraded") is True

    # /me should show plan = pro
    me = client.get("/me", headers=auth_headers)
    assert me.status_code == 200, me.text
    assert me.json()["plan_window"]["plan"] == "pro"

    # Secure call should work again
    r = _hit_secure_outlier(client, auth_headers)
    assert r.status_code == 200, r.text


def test_pro_limit_enforced_20_per_24h(client, auth_headers, db_seed):
    # Upgrade first
    b = client.post("/billing/create-checkout-session", headers=auth_headers)
    assert b.status_code == 200, b.text
    assert b.json().get("dev_upgraded") is True

    # 20 should pass
    for _ in range(20):
        r = _hit_secure_outlier(client, auth_headers)
        assert r.status_code == 200, r.text

    # 21st should block
    r21 = _hit_secure_outlier(client, auth_headers)
    assert r21.status_code == 402, r21.text