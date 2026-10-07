"use client";

import { useAuth, useClerk, useUser } from "@clerk/nextjs";
import { createContext, useCallback, useContext, useMemo, useSyncExternalStore } from "react";

import { AUTH_MODE } from "./config";

export interface AuthState {
  status: "loading" | "signed-in" | "signed-out";
  email: string | null;
  getHeaders: () => Promise<Record<string, string>>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function useAuthState(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuthState must be used inside <AuthProvider>");
  return ctx;
}

// ---- Dev mode: the email is kept in localStorage and sent as X-Dev-User-Email. ----

const DEV_EMAIL_KEY = "contraict.devEmail";
const listeners = new Set<() => void>();

function readDevEmail(): string | null {
  try {
    return window.localStorage.getItem(DEV_EMAIL_KEY);
  } catch {
    return null;
  }
}

export function setDevEmail(email: string | null) {
  try {
    if (email) window.localStorage.setItem(DEV_EMAIL_KEY, email);
    else window.localStorage.removeItem(DEV_EMAIL_KEY);
  } catch {
    // Storage unavailable (private mode): the session lasts until reload.
  }
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function DevAuthProvider({ children }: { children: React.ReactNode }) {
  // undefined on the server → "loading" until hydrated.
  const email = useSyncExternalStore(subscribe, readDevEmail, () => undefined);
  const value = useMemo<AuthState>(
    () => ({
      status: email === undefined ? "loading" : email ? "signed-in" : "signed-out",
      email: email ?? null,
      getHeaders: async (): Promise<Record<string, string>> =>
        email ? { "X-Dev-User-Email": email } : {},
      signOut: async () => setDevEmail(null),
    }),
    [email],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// ---- Clerk mode: bearer token from the Clerk session. ----

function ClerkAuthProvider({ children }: { children: React.ReactNode }) {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const { user } = useUser();
  const clerk = useClerk();
  const getHeaders = useCallback(async (): Promise<Record<string, string>> => {
    const token = await getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, [getToken]);
  const value = useMemo<AuthState>(
    () => ({
      status: !isLoaded ? "loading" : isSignedIn ? "signed-in" : "signed-out",
      email: user?.primaryEmailAddress?.emailAddress ?? null,
      getHeaders,
      signOut: () => clerk.signOut(),
    }),
    [isLoaded, isSignedIn, user, getHeaders, clerk],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  return AUTH_MODE === "clerk" ? (
    <ClerkAuthProvider>{children}</ClerkAuthProvider>
  ) : (
    <DevAuthProvider>{children}</DevAuthProvider>
  );
}
