export type AuthUser = {
  id: string;
  email?: string | null;
  user_metadata?: Record<string, unknown> | null;
};

export type AuthSession = {
  access_token: string;
  refresh_token: string;
  user: AuthUser;
};

const AUTH_SESSION_STORAGE_KEY = "difa-supabase-session";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

function getAuthHeaders() {
  return {
    apikey: SUPABASE_ANON_KEY,
    "Content-Type": "application/json",
  };
}

export function isSupabaseAuthConfigured() {
  return Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
}

export function getStoredSession(): AuthSession | null {
  if (typeof window === "undefined") {
    return null;
  }

  const raw = window.localStorage.getItem(AUTH_SESSION_STORAGE_KEY);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as AuthSession;
  } catch {
    window.localStorage.removeItem(AUTH_SESSION_STORAGE_KEY);
    return null;
  }
}

export function storeSession(session: AuthSession) {
  window.localStorage.setItem(AUTH_SESSION_STORAGE_KEY, JSON.stringify(session));
}

export function clearStoredSession() {
  window.localStorage.removeItem(AUTH_SESSION_STORAGE_KEY);
}

export function getAppUserId(session: AuthSession): string {
  const metadata = session.user.user_metadata ?? {};
  const appUserId = metadata.app_user_id;
  if (typeof appUserId === "string" && appUserId.trim()) {
    return appUserId.trim();
  }

  if (session.user.email?.trim()) {
    return session.user.email.trim();
  }

  return session.user.id;
}

type AuthResponse = {
  access_token?: string;
  refresh_token?: string;
  user?: AuthUser;
};

function toSession(data: AuthResponse): AuthSession {
  if (!data.access_token || !data.refresh_token || !data.user) {
    throw new Error("Supabase did not return an active session.");
  }

  return {
    access_token: data.access_token,
    refresh_token: data.refresh_token,
    user: data.user,
  };
}

async function parseAuthResponse(response: Response) {
  const data = (await response.json().catch(() => null)) as
    | { msg?: string; error_description?: string; error?: string }
    | null;

  if (!response.ok) {
    throw new Error(
      data?.msg || data?.error_description || data?.error || "Authentication failed."
    );
  }

  return data;
}

export async function signUpWithPassword(email: string, password: string, appUserId: string) {
  const response = await fetch(`${SUPABASE_URL}/auth/v1/signup`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({
      email,
      password,
      data: {
        app_user_id: appUserId,
      },
    }),
  });

  const data = (await parseAuthResponse(response)) as AuthResponse;
  if (!data.access_token || !data.refresh_token || !data.user) {
    return null;
  }

  const session = toSession(data);
  storeSession(session);
  return session;
}

export async function signInWithPassword(email: string, password: string) {
  const response = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ email, password }),
  });

  const data = (await parseAuthResponse(response)) as AuthResponse;
  const session = toSession(data);
  storeSession(session);
  return session;
}

export async function refreshSession(refreshToken: string) {
  const response = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=refresh_token`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  const data = (await parseAuthResponse(response)) as AuthResponse;
  const session = toSession(data);
  storeSession(session);
  return session;
}

export async function signOut(accessToken: string) {
  await fetch(`${SUPABASE_URL}/auth/v1/logout`, {
    method: "POST",
    headers: {
      ...getAuthHeaders(),
      Authorization: `Bearer ${accessToken}`,
    },
  }).catch(() => undefined);
  clearStoredSession();
}
