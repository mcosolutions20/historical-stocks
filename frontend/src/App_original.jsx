import React, { useEffect, useState } from "react";
import SearchStock from "./components/searchStockInfo";
import AuthModal from "./components/AuthModal";
import PortfolioManager from "./components/PortfolioManager";
import { setToken, me, isAuthed, previewNewsletter, sendNewsletter } from "./api";

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
    <div>
      <div className="border-bottom bg-light">
        <div className="container py-2 d-flex align-items-center justify-content-between">
          <div className="fw-semibold">CURRENT_HISTORICAL_STOCKS</div>

          <div className="d-flex align-items-center gap-2">
            {userInfo && planInfo ? (
              <>
                <span className="text-muted small">
                  {userInfo.username} • {planInfo.plan.toUpperCase()} • used {planInfo.searches_used} /{" "}
                  {planInfo.limit}
                </span>

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

      {toast && (
        <div className="container mt-3">
          <div className="alert alert-success py-2 mb-0">{toast}</div>
        </div>
      )}

      {authError && (
        <div className="container mt-3">
          <div className="alert alert-warning">{authError}</div>
        </div>
      )}

      {newsletterPreview && (
        <div className="container mt-3">
          <div className="card shadow-sm">
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
        </div>
      )}

      {/* NEW: Portfolio CRUD */}
      <PortfolioManager userInfo={userInfo} />

      {/* Existing stock search UI */}
      <SearchStock onAuthChanged={refreshMe} userInfo={userInfo} planInfo={planInfo} />

      <AuthModal isOpen={authOpen} toggle={toggleAuth} onAuthed={() => refreshMe()} />
    </div>
  );
}
