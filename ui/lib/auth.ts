"use client";

// Static-credential auth STAND-IN (no real auth yet). A single shared password
// gates entry; the email selects which seeded user you act as (drives tenancy via
// X-User-Email). Swap this whole file for real auth later — nothing else changes.
import { api } from "@/lib/api";
import { setActingUser } from "@/lib/currentUser";

const AUTH_KEY = "cadence_authed";
export const STATIC_PASSWORD =
  process.env.NEXT_PUBLIC_LOGIN_PASSWORD || "grabon@123";

export function isAuthed(): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem(AUTH_KEY) === "1";
}

export async function login(email: string, password: string): Promise<{ ok: boolean; error?: string }> {
  if (password !== STATIC_PASSWORD) return { ok: false, error: "Incorrect password." };
  const clean = email.trim().toLowerCase();
  if (!clean) return { ok: false, error: "Enter your email." };
  // Resolve which seeded user this email maps to (for role + tenancy). Falls back
  // to a plain member identity if the list can't be loaded.
  let is_admin = false;
  let name: string | null = clean;
  try {
    const users = await api.usersList();
    const u = users.find((x) => (x.email || "").toLowerCase() === clean);
    if (u) { is_admin = !!u.is_admin; name = u.name; }
  } catch {
    /* offline / no list — proceed as a member */
  }
  setActingUser({ email: clean, is_admin, name });
  if (typeof window !== "undefined") localStorage.setItem(AUTH_KEY, "1");
  return { ok: true };
}

export function logout(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(AUTH_KEY);
}
