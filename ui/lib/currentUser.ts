"use client";

// Pre-auth "who am I acting as" store. This is the ONLY client-side stand-in for
// authentication: it records the simulated current user's email + admin flag, which
// the API client sends as X-User-Email (tenancy) and X-Role (admin dashboard).
// Real auth later replaces this entirely — business logic stays the same.

export interface ActingUser {
  email: string | null; // null → backend default (GrabOn Platform Admin)
  is_admin: boolean;
  name?: string | null;
}

const KEY = "growthos_acting_user";

export function getActingUser(): ActingUser {
  if (typeof window === "undefined") return { email: null, is_admin: true };
  try {
    const v = localStorage.getItem(KEY);
    if (v) return JSON.parse(v) as ActingUser;
  } catch {
    /* ignore */
  }
  return { email: null, is_admin: true }; // default = GrabOn Platform Admin
}

export function setActingUser(u: ActingUser): void {
  if (typeof window !== "undefined") localStorage.setItem(KEY, JSON.stringify(u));
}
