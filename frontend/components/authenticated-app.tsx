"use client";

import { FormEvent, useEffect, useState } from "react";
import { LockKeyhole, LogOut, ShieldCheck } from "lucide-react";

import { DocumentIntelligenceApp } from "@/components/document-intelligence-app";

const AUTH_STORAGE_KEY = "difa-authenticated";

const VALID_USERNAME = process.env.NEXT_PUBLIC_APP_USERNAME ?? "";
const VALID_PASSWORD = process.env.NEXT_PUBLIC_APP_PASSWORD ?? "";

export function AuthenticatedApp() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isHydrated, setIsHydrated] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const stored = window.localStorage.getItem(AUTH_STORAGE_KEY);
    setIsAuthenticated(stored === "true");
    setIsHydrated(true);
  }, []);

  function handleLogout() {
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
    setIsAuthenticated(false);
  }

  function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const username = String(formData.get("username") ?? "").trim();
    const password = String(formData.get("password") ?? "");

    if (!VALID_USERNAME || !VALID_PASSWORD) {
      setError("Frontend credentials are not configured yet.");
      return;
    }

    if (username !== VALID_USERNAME || password !== VALID_PASSWORD) {
      setError("Incorrect username or password.");
      return;
    }

    window.localStorage.setItem(AUTH_STORAGE_KEY, "true");
    setError(null);
    setIsAuthenticated(true);
    form.reset();
  }

  if (!isHydrated) {
    return <div className="auth-shell" />;
  }

  if (!isAuthenticated) {
    return (
      <main className="auth-shell">
        <section className="auth-card">
          <div className="auth-copy">
            <p className="eyebrow">DIFA Workspace</p>
            <h1>Document intelligence for focused accounting review.</h1>
            <p>
              Upload long PDFs, inspect each page visually, annotate key sections, regenerate
              summaries, and ask page-specific questions when the details matter.
            </p>

            <div className="auth-highlights">
              <div className="auth-highlight">
                <ShieldCheck size={18} />
                <span>Page-level summaries with accountant-first takeaways</span>
              </div>
              <div className="auth-highlight">
                <LockKeyhole size={18} />
                <span>Highlights, notes, and page Q&A in one calm review space</span>
              </div>
            </div>
          </div>

          <form className="auth-form" onSubmit={handleLogin}>
            <div className="auth-form-head">
              <span className="section-label">Secure Sign-In</span>
              <h2>Welcome back</h2>
            </div>

            <label className="auth-field">
              <span>Username</span>
              <input autoComplete="username" name="username" type="text" />
            </label>

            <label className="auth-field">
              <span>Password</span>
              <input autoComplete="current-password" name="password" type="password" />
            </label>

            {error ? <div className="error">{error}</div> : null}

            <button className="button auth-submit" type="submit">
              <LockKeyhole size={16} />
              Sign in
            </button>
          </form>
        </section>
      </main>
    );
  }

  return (
    <>
      <div className="workspace-topbar">
        <div className="workspace-topbar-copy">
          <span className="section-label">DIFA</span>
          <span className="muted">Private review workspace</span>
        </div>

        <button className="button button-secondary" onClick={handleLogout} type="button">
          <LogOut size={16} />
          Log out
        </button>
      </div>
      <DocumentIntelligenceApp />
    </>
  );
}
