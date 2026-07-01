"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { isAuthed } from "@/lib/auth";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ok, setOk] = useState(false);

  useEffect(() => {
    if (isAuthed()) setOk(true);
    else router.replace("/login");
  }, [router]);

  if (!ok) return null; // avoid flashing protected content before the redirect
  return <>{children}</>;
}
