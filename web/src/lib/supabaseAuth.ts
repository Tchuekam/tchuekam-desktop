const DEFAULT_SUPABASE_URL = "https://fzoiiusuqvjhwivstbyb.supabase.co";
const DEFAULT_SUPABASE_ANON_KEY =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZ6b2lpdXN1cXZqaHdpdnN0YnliIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQyNDgxNjUsImV4cCI6MjA5OTgyNDE2NX0.CH6Z7CxPaRxND2fivpcGu42RFmo8uxyBeeoeTuGEPCI";
const DEFAULT_AUTH_PORTAL_URL = "http://localhost:3000";

const STORAGE_KEY = "tchuekam.supabase.session";

export interface StoredSupabaseSession {
  access_token: string;
  refresh_token?: string;
  expires_at?: number;
  token_type?: string;
}

export interface SupabaseUserInfo {
  id: string;
  email: string;
  user_metadata?: {
    full_name?: string;
    username?: string;
    company_name?: string;
  };
  app_metadata?: {
    provider?: string;
  };
  last_sign_in_at?: string;
}

export function getSupabaseConfig() {
  const env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env || {};
  let defaultPortalUrl = DEFAULT_AUTH_PORTAL_URL;
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host && host !== "localhost" && host !== "127.0.0.1") {
      defaultPortalUrl = "https://auth.tchuekam.com";
    }
  }
  return {
    supabaseUrl: (env.VITE_SUPABASE_URL || DEFAULT_SUPABASE_URL).replace(/\/+$/, ""),
    supabaseAnonKey: env.VITE_SUPABASE_ANON_KEY || DEFAULT_SUPABASE_ANON_KEY,
    authPortalUrl: (env.VITE_AUTH_PORTAL_URL || defaultPortalUrl).replace(/\/+$/, ""),
  };
}

export function captureSupabaseHashSession(): StoredSupabaseSession | null {
  if (typeof window === "undefined") return null;
  const rawHash = window.location.hash;
  if (!rawHash || !rawHash.includes("access_token=")) return null;

  const params = new URLSearchParams(rawHash.slice(1));
  const accessToken = params.get("access_token");
  if (!accessToken) return null;

  const expiresAtRaw = params.get("expires_at");
  const session: StoredSupabaseSession = {
    access_token: accessToken,
    refresh_token: params.get("refresh_token") || undefined,
    expires_at: expiresAtRaw ? Number(expiresAtRaw) : undefined,
    token_type: params.get("token_type") || "bearer",
  };

  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Ignore storage failures in strict privacy mode
  }

  // Strip tokens from browser address bar immediately
  try {
    window.history.replaceState(
      null,
      "",
      window.location.pathname + window.location.search,
    );
  } catch {
    // Best effort
  }

  return session;
}

export function isSupabaseSessionExpired(sess: StoredSupabaseSession | null): boolean {
  return Boolean(sess?.expires_at && sess.expires_at * 1000 <= Date.now() + 10_000);
}

export function getStoredSupabaseSession(): StoredSupabaseSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredSupabaseSession;
    if (!parsed?.access_token) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function getStoredSupabaseAccessToken(): string | null {
  const sess = getStoredSupabaseSession();
  if (!sess || isSupabaseSessionExpired(sess)) return null;
  return sess.access_token;
}

export function clearSupabaseSession(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Ignore
  }
}

export async function refreshSupabaseSessionIfNeeded(
  sess: StoredSupabaseSession,
): Promise<StoredSupabaseSession | null> {
  if (!sess.expires_at || sess.expires_at * 1000 > Date.now() + 30_000) {
    return sess;
  }
  if (!sess.refresh_token) {
    clearSupabaseSession();
    return null;
  }

  const { supabaseUrl, supabaseAnonKey } = getSupabaseConfig();
  try {
    const res = await fetch(`${supabaseUrl}/auth/v1/token?grant_type=refresh_token`, {
      method: "POST",
      headers: {
        apikey: supabaseAnonKey,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ refresh_token: sess.refresh_token }),
    });
    if (!res.ok) {
      clearSupabaseSession();
      return null;
    }
    const data = await res.json();
    const updated: StoredSupabaseSession = {
      access_token: data.access_token,
      refresh_token: data.refresh_token || sess.refresh_token,
      expires_at: data.expires_at || Math.floor(Date.now() / 1000) + (data.expires_in || 3600),
      token_type: data.token_type || "bearer",
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    return updated;
  } catch {
    return sess;
  }
}

export async function fetchSupabaseUser(): Promise<SupabaseUserInfo | null> {
  captureSupabaseHashSession();
  const initial = getStoredSupabaseSession();
  if (!initial) return null;

  const active = await refreshSupabaseSessionIfNeeded(initial);
  if (!active) return null;

  const { supabaseUrl, supabaseAnonKey } = getSupabaseConfig();
  try {
    const res = await fetch(`${supabaseUrl}/auth/v1/user`, {
      headers: {
        apikey: supabaseAnonKey,
        Authorization: `Bearer ${active.access_token}`,
      },
    });
    if (res.status === 401 || res.status === 403) {
      clearSupabaseSession();
      return null;
    }
    if (!res.ok) return null;
    return (await res.json()) as SupabaseUserInfo;
  } catch {
    return null;
  }
}

export async function signOutSupabase(): Promise<void> {
  const token = getStoredSupabaseAccessToken();
  const { supabaseUrl, supabaseAnonKey } = getSupabaseConfig();
  clearSupabaseSession();
  if (!token) return;

  try {
    await fetch(`${supabaseUrl}/auth/v1/logout`, {
      method: "POST",
      headers: {
        apikey: supabaseAnonKey,
        Authorization: `Bearer ${token}`,
      },
    });
  } catch {
    // Best effort remote revocation
  }
}

export function getAuthPortalUrl(path: "/login" | "/register" | "/" = "/login"): string {
  const { authPortalUrl } = getSupabaseConfig();
  if (typeof window === "undefined" || path === "/") {
    return `${authPortalUrl}${path === "/" ? "" : path}`;
  }
  const returnUrl = window.location.origin + window.location.pathname + window.location.search;
  return `${authPortalUrl}${path}?redirect_to=${encodeURIComponent(returnUrl)}`;
}
