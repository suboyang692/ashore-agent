import type { Session } from "./api";

const KEY = "ashore.session.v1";

export function loadSession(): Session | null {
  try {
    const value = sessionStorage.getItem(KEY);
    if (!value) return null;
    const parsed: unknown = JSON.parse(value);
    if (parsed && typeof parsed === "object" && "token" in parsed && "user" in parsed &&
        typeof parsed.token === "string" && parsed.user && typeof parsed.user === "object" &&
        "id" in parsed.user && typeof parsed.user.id === "string") {
      return parsed as Session;
    }
  } catch { /* Invalid or unavailable storage */ }
  return null;
}

export function saveSession(session: Session | null) {
  try {
    if (session) sessionStorage.setItem(KEY, JSON.stringify(session));
    else sessionStorage.removeItem(KEY);
  } catch { /* Private browsing may disable storage */ }
}
