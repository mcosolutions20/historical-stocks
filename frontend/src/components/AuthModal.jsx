import React, { useState } from "react";
import { Modal, ModalHeader, ModalBody } from "reactstrap";
import { register, login, setToken } from "../api";
import { GoogleLogin } from "@react-oauth/google";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

export default function AuthModal({ isOpen, toggle, onAuthed }) {
  const [tab, setTab] = useState("login");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [demoVerifyUrl, setDemoVerifyUrl] = useState("");

  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [regPassword, setRegPassword] = useState("");

  const [usernameOrEmail, setUsernameOrEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");

  async function handleRegister(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await register({ email, username, password: regPassword });
      if (res?.message) setDemoVerifyUrl("Check your email to verify.");
    } catch (err) {
      setError(err?.response?.data?.detail || "Register failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleLogin(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await login({ username_or_email: usernameOrEmail, password: loginPassword });
      if (res?.access_token) {
        setToken(res.access_token);
        onAuthed?.();
        toggle();
      }
    } catch (err) {
      setError(err?.response?.data?.detail || "Login failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleGoogleSuccess(credentialResponse) {
    setError("");
    try {
      const res = await axios.post(`${API_BASE}/auth/google`, {
        id_token: credentialResponse.credential,
      });

      if (res.data?.access_token) {
        setToken(res.data.access_token);
        onAuthed?.();
        toggle();
      }
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const msg =
        (typeof detail === "string" && detail) ||
        detail?.message ||
        err?.message ||
        "Google sign-in failed";
      setError(String(msg));
    }
  }

  return (
    <Modal isOpen={isOpen} toggle={toggle} centered>
      <ModalHeader toggle={toggle}>Account</ModalHeader>
      <ModalBody>

        {/* Google Sign-In */}
        <div className="mb-3 text-center">
          <GoogleLogin
            onSuccess={handleGoogleSuccess}
            onError={() => setError("Google sign-in failed")}
            ux_mode="popup"
          />
        </div>

        <hr />

        <div className="btn-group w-100 mb-3">
          <button className={`btn btn-sm ${tab === "login" ? "btn-primary" : "btn-outline-primary"}`}
            onClick={() => setTab("login")}>
            Login
          </button>
          <button className={`btn btn-sm ${tab === "register" ? "btn-primary" : "btn-outline-primary"}`}
            onClick={() => setTab("register")}>
            Register
          </button>
        </div>

        {error && <div className="alert alert-danger">{error}</div>}

        {tab === "register" ? (
          <form onSubmit={handleRegister} className="d-grid gap-2">
            <input className="form-control" placeholder="Email" value={email}
              onChange={(e) => setEmail(e.target.value)} />
            <input className="form-control" placeholder="Username" value={username}
              onChange={(e) => setUsername(e.target.value)} />
            <input className="form-control" type="password" placeholder="Password"
              value={regPassword} onChange={(e) => setRegPassword(e.target.value)} />
            <button className="btn btn-primary" disabled={loading}>Create account</button>
            {demoVerifyUrl && <div className="text-muted small">{demoVerifyUrl}</div>}
          </form>
        ) : (
          <form onSubmit={handleLogin} className="d-grid gap-2">
            <input className="form-control" placeholder="Username or Email"
              value={usernameOrEmail} onChange={(e) => setUsernameOrEmail(e.target.value)} />
            <input className="form-control" type="password" placeholder="Password"
              value={loginPassword} onChange={(e) => setLoginPassword(e.target.value)} />
            <button className="btn btn-primary" disabled={loading}>Login</button>
          </form>
        )}
      </ModalBody>
    </Modal>
  );
}
