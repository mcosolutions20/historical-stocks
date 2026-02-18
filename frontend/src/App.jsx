import React, { useEffect, useState } from "react";
import SearchStock from "./components/searchStockInfo";
import AuthModal from "./components/AuthModal";
import PortfolioManager from "./components/PortfolioManager";
import { setToken, me, isAuthed, previewNewsletter, sendNewsletter, createCheckoutSession } from "./api";


export default function App() {
  const [authOpen, setAuthOpen] = useState(false);
  const [userInfo, setUserInfo] = useState(null);
  const [planInfo, setPlanInfo] = useState(null);
  const [authError, setAuthError] = useState("");
  const [toast, setToast] = useState("");
  const [newsletterPreview, setNewsletterPreview] = useState("");

  function toggleAuth() {
    setAuthOpen((v) => !v);
  }

  async function refreshMe() {
    setAuthError("");
    if (!isAuthed()) {
      setUserInfo(null);
      setPlanInfo(null);
      return;
    }
    try {
      const res = await me();
      setUserInfo(res.user);
      setPlanInfo(res.plan_window);
    } catch (err) {
      setAuthError("Session invalid. Please login again.");
      setToken(null);
      setUserInfo(null);
      setPlanInfo(null);
    }
  }

  function clearQueryParam(name) {
    const url = new URL(window.location.href);
    if (url.searchParams.has(name)) {
      url.searchParams.delete(name);
      window.history.replaceState({}, "", url.toString());
      return true;
    }
    return false;
  }

  useEffect(() => {
    (async () => {
      await refreshMe();

      const url = new URL(window.location.href);
      const checkout = url.searchParams.get("checkout");

      if (checkout === "success") {
        setToast("Payment successful — upgrading plan…");
        setTimeout(async () => {
          await refreshMe();
          setToast("Upgrade applied. You’re on PRO!");
          setTimeout(() => setToast(""), 2500);
        }, 1200);
        clearQueryParam("checkout");
      }

      if (checkout === "cancel") {
        setToast("Checkout canceled.");
        setTimeout(() => setToast(""), 2500);
        clearQueryParam("checkout");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleLogout() {
    setToken(null);
    setUserInfo(null);
    setPlanInfo(null);
    setNewsletterPreview("");
  }

  async function handleUpgrade() {
    try {
      const res = await createCheckoutSession();

      // Stripe path
      if (res?.url) {
        window.location.href = res.url;
        return;
      }

      // Dev bypass path
      if (res?.dev_upgraded) {
        setToast("Dev mode: upgraded to PRO (Stripe bypass).");
        await refreshMe();
        setTimeout(() => setToast(""), 2500);
        return;
      }

      setToast("Upgrade is not available right now (no checkout URL returned).");
      setTimeout(() => setToast(""), 2500);
    } catch (err) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;

      if (status === 501 && detail?.code === "billing_not_configured") {
        setToast("Billing not configured in this environment.");
        setTimeout(() => setToast(""), 2500);
        return;
      }

      const msg =
        detail?.message ||
        detail?.detail ||
        err?.response?.data?.detail ||
        err?.message ||
        "Upgrade failed.";

      setToast(String(msg));
      setTimeout(() => setToast(""), 2500);
    }
  }

  async function handlePreviewNewsletter() {
    try {
      setToast("Generating preview…");
      const res = await previewNewsletter();
      setNewsletterPreview(res.newsletter || "");
      setToast("");
    } catch (e) {
      const msg = e?.response?.data?.detail || "Failed to generate newsletter preview.";
      setToast(msg);
      setTimeout(() => setToast(""), 2500);
    }
  }

  async function handleSendNewsletter() {
    try {
      const text = (newsletterPreview || "").trim();
      if (!text) {
        setToast("Generate a preview first.");
        setTimeout(() => setToast(""), 2000);
        return;
      }

      setToast("Sending newsletter…");
      await sendNewsletter(text);
      setToast("Sent! Check your inbox.");
      setTimeout(() => setToast(""), 2500);
    } catch (e) {
      const msg = e?.response?.data?.detail || "Failed to send newsletter.";
      setToast(msg);
      setTimeout(() => setToast(""), 2500);
    }
  }

  const canNewsletter = !!userInfo?.is_verified;

  return (
    <div className="app-page">
        <div className="border-bottom bg-white sticky-top">
        <div className="container py-2 d-flex align-items-center justify-content-between">
            <div className="fw-semibold">CURRENT_HISTORICAL_STOCKS</div>

            <div className="d-flex align-items-center gap-2">
            {userInfo && planInfo ? (
                <>
                <span className="text-muted small">
                    {userInfo.username} • {planInfo.plan.toUpperCase()} • used {planInfo.searches_used} / {planInfo.limit}
                </span>
                {planInfo?.plan === "free" && (
                  <div className="d-flex align-items-center gap-2">
                    <button className="btn btn-sm btn-warning" onClick={() =>{
                      navigator.clipboard?.writeText("4242424242424242");
                      alert("Copied test card number: 4242 4242 4242 4242\n\nUse this card number with any future expiry date and any CVC in the Stripe checkout form.");
                      handleUpgrade();}}>
                      Upgrade (demo checkout)
                    </button>
                  </div>
                )}


                <button className="btn btn-sm btn-outline-secondary" onClick={refreshMe}>
                    Refresh
                </button>

                <button
                    className="btn btn-sm btn-outline-primary"
                    onClick={handlePreviewNewsletter}
                    disabled={!canNewsletter}
                    title={!canNewsletter ? "Verify email to use newsletter" : ""}
                >
                    Preview Newsletter
                </button>

                <button
                    className="btn btn-sm btn-primary"
                    onClick={handleSendNewsletter}
                    disabled={!canNewsletter}
                    title={!canNewsletter ? "Verify email to use newsletter" : ""}
                >
                    Send Newsletter
                </button>

                <button className="btn btn-sm btn-outline-danger" onClick={handleLogout}>
                    Logout
                </button>
                </>
            ) : (
                <button className="btn btn-sm btn-primary" onClick={toggleAuth}>
                Login / Register
                </button>
            )}
            </div>
        </div>
        </div>

        <main className="container my-4">
        {toast && (
            <div className="alert alert-success py-2">{toast}</div>
        )}

        {authError && (
            <div className="alert alert-warning">{authError}</div>
        )}

        {newsletterPreview && (
            <div className="card shadow-sm mb-3">
            <div className="card-body">
                <div className="d-flex justify-content-between align-items-center mb-2">
                <div className="fw-semibold">Newsletter Preview</div>
                <button className="btn btn-sm btn-outline-secondary" onClick={() => setNewsletterPreview("")}>
                    Close
                </button>
                </div>
                <pre className="mb-0" style={{ whiteSpace: "pre-wrap" }}>
                {newsletterPreview}
                </pre>
            </div>
            </div>
        )}

        <div className="app-shell">
            <PortfolioManager userInfo={userInfo} />
            <hr className="my-4" />
            <SearchStock onAuthChanged={refreshMe} userInfo={userInfo} planInfo={planInfo} />
        </div>
        </main>

        <AuthModal isOpen={authOpen} toggle={toggleAuth} onAuthed={() => refreshMe()} />
    </div>
    );

}
