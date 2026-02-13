import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";
const TOKEN_KEY = "auth:token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (!token) localStorage.removeItem(TOKEN_KEY);
  else localStorage.setItem(TOKEN_KEY, token);
}

export function isAuthed() {
  return !!getToken();
}

function authHeaders() {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

/** Meta */
export async function fetchMeta() {
  const res = await axios.get(`${API_BASE}/meta`);
  return res.data;
}

/** Auth */
export async function register({ email, username, password }) {
  const res = await axios.post(`${API_BASE}/auth/register`, { email, username, password });
  return res.data;
}

export async function login({ username_or_email, password }) {
  const res = await axios.post(`${API_BASE}/auth/login`, { username_or_email, password });
  return res.data;
}

export async function verifyEmail(token) {
  const res = await axios.get(`${API_BASE}/auth/verify/${token}`);
  return res.data;
}

export async function resendVerification(email) {
  const res = await axios.post(`${API_BASE}/auth/resend-verification`, { email });
  return res.data;
}

export async function googleSignIn(id_token) {
  const res = await axios.post(`${API_BASE}/auth/google`, { id_token });
  return res.data;
}

export async function me() {
  const res = await axios.get(`${API_BASE}/me`, { headers: authHeaders() });
  return res.data;
}

/** Billing */
export async function createCheckoutSession() {
  const res = await axios.post(`${API_BASE}/billing/create-checkout-session`, {}, { headers: authHeaders() });
  return res.data;
}

/** Newsletter */
export async function previewNewsletter() {
  const res = await axios.get(`${API_BASE}/newsletter/preview`, { headers: authHeaders() });
  return res.data;
}

export async function sendNewsletter(newsletterText) {
  const res = await axios.post(
    `${API_BASE}/newsletter/send`,
    { newsletter: newsletterText },
    { headers: authHeaders() }
  );
  return res.data;
}

/** Public endpoints */
export async function fetchStock({ startDate, endDate, ticker }) {
  const start = fmtDate(startDate);
  const end = fmtDate(endDate);
  const res = await axios.get(`${API_BASE}/stock/${start}/${end}/${ticker}`);
  return res.data;
}

export async function fetchOutliers({ startDate, endDate, performance, quantity }) {
  const start = fmtDate(startDate);
  const end = fmtDate(endDate);
  const res = await axios.get(`${API_BASE}/outlier/${start}/${end}/${performance}/${quantity}`);
  return res.data;
}

/** Secure endpoints */
export async function fetchStockSecure({ startDate, endDate, ticker }) {
  const start = fmtDate(startDate);
  const end = fmtDate(endDate);
  const res = await axios.get(`${API_BASE}/secure/stock/${start}/${end}/${ticker}`, { headers: authHeaders() });
  return res.data;
}

export async function fetchOutliersSecure({ startDate, endDate, performance, quantity }) {
  const start = fmtDate(startDate);
  const end = fmtDate(endDate);
  const res = await axios.get(
    `${API_BASE}/secure/outlier/${start}/${end}/${performance}/${quantity}`,
    { headers: authHeaders() }
  );
  return res.data;
}

/** Portfolio CRUD */
export async function listPortfolios() {
  const res = await axios.get(`${API_BASE}/portfolios`, { headers: authHeaders() });
  return res.data;
}

export async function createPortfolio(name, cash_balance = 0) {
  const res = await axios.post(`${API_BASE}/portfolios`, { name, cash_balance }, { headers: authHeaders() });
  return res.data;
}

export async function getPortfolio(portfolioId) {
  const res = await axios.get(`${API_BASE}/portfolios/${portfolioId}`, { headers: authHeaders() });
  return res.data;
}

export async function updatePortfolio(portfolioId, { name, cash_balance }) {
  const res = await axios.put(
    `${API_BASE}/portfolios/${portfolioId}`,
    { name, cash_balance },
    { headers: authHeaders() }
  );
  return res.data;
}

export async function deletePortfolio(portfolioId) {
  const res = await axios.delete(`${API_BASE}/portfolios/${portfolioId}`, { headers: authHeaders() });
  return res.data;
}

/** Transactions */
export async function listTransactions(portfolioId) {
  const res = await axios.get(`${API_BASE}/portfolios/${portfolioId}/transactions`, { headers: authHeaders() });
  return res.data;
}

export async function createTransaction(portfolioId, { ticker, side, shares, price, trade_date, notes }) {
  const payload = { ticker, side, shares, trade_date, notes };

  // Allow price to be blank. If price is null/undefined/"" the backend auto-fills from your DB.
  if (price === null || price === undefined || price === "") {
    payload.price = null;
  } else {
    payload.price = price;
  }

  const res = await axios.post(`${API_BASE}/portfolios/${portfolioId}/transactions`, payload, { headers: authHeaders() });
  return res.data;
}

export async function deleteTransaction(transactionId) {
  const res = await axios.delete(`${API_BASE}/transactions/${transactionId}`, { headers: authHeaders() });
  return res.data;
}


export async function exportTransactionsCsv(portfolioId) {
  const res = await axios.get(`${API_BASE}/portfolios/${portfolioId}/transactions/export`, {
    headers: authHeaders(),
    responseType: "blob",
  });
  return res;
}

export async function importTransactionsCsv(portfolioId, file) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await axios.post(`${API_BASE}/portfolios/${portfolioId}/transactions/import`, fd, {
    headers: { ...authHeaders(), "Content-Type": "multipart/form-data" },
  });
  return res.data;
}

/** Valuation */
export async function getPortfolioValuation(portfolioId) {
  const res = await axios.get(`${API_BASE}/portfolios/${portfolioId}/valuation`, { headers: authHeaders() });
  return res.data;
}

/** Performance */
export async function getPortfolioPerformance(portfolioId, { start, end, benchmark = "SP500" }) {
  const res = await axios.get(`${API_BASE}/portfolios/${portfolioId}/performance`, {
    headers: authHeaders(),
    params: { start, end, benchmark },
  });
  return res.data;
}

export async function exportPortfolioPerformanceCsv(portfolioId, { start, end, benchmark = "SP500" }) {
  const res = await axios.get(`${API_BASE}/portfolios/${portfolioId}/performance/export`, {
    headers: authHeaders(),
    params: { start, end, benchmark },
    responseType: "blob",
  });
  return res;
}

/** Rebalance */
export async function rebalancePortfolio(portfolioId, { targets, include_cash_in_total = true }) {
  const res = await axios.post(
    `${API_BASE}/portfolios/${portfolioId}/rebalance`,
    { targets, include_cash_in_total },
    { headers: authHeaders() }
  );
  return res.data;
}

/** utils */
function fmtDate(d) {
  if (!d) return "";
  const dt = new Date(d);
  const y = dt.getFullYear();
  const m = String(dt.getMonth() + 1).padStart(2, "0");
  const day = String(dt.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}
