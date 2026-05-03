"use client";

import { FormEvent, useEffect, useState } from "react";
import { LockKeyhole, LogOut, ShieldCheck, UserPlus } from "lucide-react";

import { DocumentIntelligenceApp } from "@/components/document-intelligence-app";
import {
  clearStoredSession,
  getAppUserId,
  getStoredSession,
  isSupabaseAuthConfigured,
  refreshSession,
  signInWithPassword,
  signOut,
  signUpWithPassword,
  type AuthSession,
} from "@/lib/supabase-auth";

const AUTH_STORAGE_KEY = "difa-authenticated";
const AUTH_USER_STORAGE_KEY = "difa-authenticated-user";

const VALID_USERNAME = process.env.NEXT_PUBLIC_APP_USERNAME ?? "";
const VALID_PASSWORD = process.env.NEXT_PUBLIC_APP_PASSWORD ?? "";

type AuthMode = "signin" | "signup";

export function AuthenticatedApp() {
  const [isHydrated, setIsHydrated] = useState(false);
  const [mode, setMode] = useState<AuthMode>("signin");
  const [legacyAuthenticated, setLegacyAuthenticated] = useState(false);
  const [legacyUserId, setLegacyUserId] = useState("");
  const [session, setSession] = useState<AuthSession | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isSupabaseMode = isSupabaseAuthConfigured();

  useEffect(() => {
    async function hydrate() {
      if (isSupabaseMode) {
        const storedSession = getStoredSession();
        if (storedSession) {
          try {
            const refreshedSession = await refreshSession(storedSession.refresh_token);
            setSession(refreshedSession);
          } catch {
            clearStoredSession();
            setSession(null);
          }
        }
        setIsHydrated(true);
        return;
      }

      const stored = window.localStorage.getItem(AUTH_STORAGE_KEY);
      const storedUser = window.localStorage.getItem(AUTH_USER_STORAGE_KEY) ?? "";
      setLegacyAuthenticated(stored === "true");
      setLegacyUserId(storedUser);
      setIsHydrated(true);
    }

    void hydrate();
  }, [isSupabaseMode]);

  async function handleLogout() {
    if (isSupabaseMode) {
      if (session) {
        await signOut(session.access_token);
      } else {
        clearStoredSession();
      }
      setSession(null);
      return;
    }

    window.localStorage.removeItem(AUTH_STORAGE_KEY);
    window.localStorage.removeItem(AUTH_USER_STORAGE_KEY);
    setLegacyAuthenticated(false);
    setLegacyUserId("");
  }

  async function handleSupabaseAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const email = String(formData.get("email") ?? "").trim();
    const password = String(formData.get("password") ?? "");
    const confirmPassword = String(formData.get("confirmPassword") ?? "");
    const appUserId = String(formData.get("appUserId") ?? "").trim();

    if (!email || !password) {
      setError("Enter your email and password.");
      return;
    }

    if (mode === "signup" && !appUserId) {
      setError("Choose a workspace username for file ownership.");
      return;
    }

    if (mode === "signup" && password !== confirmPassword) {
      setError("Password and confirm password must match.");
      return;
    }

    setIsBusy(true);
    setError(null);

    try {
      if (mode === "signup") {
        const nextSession = await signUpWithPassword(email, password, appUserId);
        if (!nextSession) {
          setMode("signin");
          setError("Sign-up succeeded. If email confirmation is enabled, confirm it and then sign in.");
          return;
        }
        setSession(nextSession);
      } else {
        const nextSession = await signInWithPassword(email, password);
        setSession(nextSession);
      }
      form.reset();
    } catch (authError) {
      setError(getMessage(authError));
    } finally {
      setIsBusy(false);
    }
  }

  function handleLegacyLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const username = String(formData.get("username") ?? "").trim();
    const password = String(formData.get("password") ?? "");

    if (!VALID_USERNAME || !VALID_PASSWORD) {
      setError("Legacy frontend credentials are not configured.");
      return;
    }

    if (username !== VALID_USERNAME || password !== VALID_PASSWORD) {
      setError("Incorrect username or password.");
      return;
    }

    window.localStorage.setItem(AUTH_STORAGE_KEY, "true");
    window.localStorage.setItem(AUTH_USER_STORAGE_KEY, username);
    setError(null);
    setLegacyAuthenticated(true);
    setLegacyUserId(username);
    form.reset();
  }

  if (!isHydrated) {
    return <div className="auth-shell" />;
  }

  const effectiveUserId = isSupabaseMode
    ? (session ? getAppUserId(session) : "")
    : (legacyUserId || VALID_USERNAME);
  const isAuthenticated = isSupabaseMode ? Boolean(session) : legacyAuthenticated;

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

          {isSupabaseMode ? (
            <form className="auth-form" onSubmit={(event) => void handleSupabaseAuth(event)}>
              <div className="auth-form-head">
                <span className="section-label">
                  {mode === "signup" ? "Create Account" : "Secure Sign-In"}
                </span>
                <h2>{mode === "signup" ? "Create your workspace login" : "Welcome back"}</h2>
              </div>

              <label className="auth-field">
                <span>Email</span>
                <input autoComplete="email" name="email" type="email" />
              </label>

              {mode === "signup" ? (
                <label className="auth-field">
                  <span>Workspace username</span>
                  <input
                    defaultValue={VALID_USERNAME}
                    name="appUserId"
                    placeholder="Used for document ownership"
                    type="text"
                  />
                </label>
              ) : null}

              <label className="auth-field">
                <span>Password</span>
                <input
                  autoComplete={mode === "signup" ? "new-password" : "current-password"}
                  name="password"
                  type="password"
                />
              </label>

              {mode === "signup" ? (
                <label className="auth-field">
                  <span>Confirm password</span>
                  <input
                    autoComplete="new-password"
                    name="confirmPassword"
                    type="password"
                  />
                </label>
              ) : null}

              {error ? <div className="error">{error}</div> : null}

              <button className="button auth-submit" disabled={isBusy} type="submit">
                {mode === "signup" ? <UserPlus size={16} /> : <LockKeyhole size={16} />}
                {isBusy ? "Please wait..." : mode === "signup" ? "Create account" : "Sign in"}
              </button>

              <button
                className="button button-secondary auth-submit"
                onClick={() => {
                  setError(null);
                  setMode((current) => (current === "signin" ? "signup" : "signin"));
                }}
                type="button"
              >
                {mode === "signup" ? "Use existing account" : "Create new account"}
              </button>
            </form>
          ) : (
            <form className="auth-form" onSubmit={handleLegacyLogin}>
              <div className="auth-form-head">
                <span className="section-label">Legacy Sign-In</span>
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
          )}
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

        <button className="button button-secondary" onClick={() => void handleLogout()} type="button">
          <LogOut size={16} />
          Log out
        </button>
      </div>
      <DocumentIntelligenceApp
        authToken={session?.access_token ?? null}
        userId={effectiveUserId}
      />
    </>
  );
}

function getMessage(error: unknown) {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "Something went wrong.";
}
