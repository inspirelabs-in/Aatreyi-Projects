import { BRAND } from "@/lib/brand";

// Brand mark: a rounded gradient tile with a stylised "cadence" wave + wordmark.
export function LogoMark({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <defs>
        <linearGradient id="cad-g" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop stopColor="#3b82f6" />
          <stop offset="1" stopColor="#7c3aed" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#cad-g)" />
      <path
        d="M6 20c3 0 3-8 6.5-8s3.5 8 6.5 8 3-8 6.5-8"
        stroke="white" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" fill="none"
      />
    </svg>
  );
}

export function Logo({ size = 32, wordmark = true }: { size?: number; wordmark?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2">
      <LogoMark size={size} />
      {wordmark && (
        <span className="text-lg font-bold tracking-tight text-slate-900">{BRAND.name}</span>
      )}
    </span>
  );
}
