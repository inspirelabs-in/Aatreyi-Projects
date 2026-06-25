"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getRole } from "@/lib/role";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [allowed, setAllowed] = useState<boolean | null>(null);

  useEffect(() => {
    if (getRole() !== "admin") {
      router.replace("/");
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
