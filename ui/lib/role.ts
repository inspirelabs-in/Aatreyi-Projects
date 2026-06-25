"use client";

export type Role = "user" | "admin";
export const ROLE_KEY = "growthos_role";

export function getRole(): Role {
  if (typeof window === "undefined") return "user";
  return (localStorage.getItem(ROLE_KEY) as Role) || "user";
}

export function setRole(r: Role): void {
  if (typeof window !== "undefined") localStorage.setItem(ROLE_KEY, r);
}
