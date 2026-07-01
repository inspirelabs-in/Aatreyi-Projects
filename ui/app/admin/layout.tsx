"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getActingUser } from "@/lib/currentUser";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [allowed, setAllowed] = useState<boolean | null>(null);

  useEffect(() => {
    // Platform-admin gate (identity comes from the acting user, not the old X-Role).
    if (!getActingUser().is_admin) {
      router.replace("/channels");
      setAllowed(false);
    } else {
      setAllowed(true);
    }
  }, [router]);

  if (allowed !== true) {
    return <div className="py-16 text-center text-sm text-slate-400">Checking admin access…</div>;
  }
  return <>{children}</>;
}
