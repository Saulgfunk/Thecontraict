import { cn } from "@/lib/utils";

/** The mark: a document with a folded corner and a tick, on a blue tile. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("size-8 shrink-0", className)}>
      <defs>
        <linearGradient id="logo-bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#4c63f0" />
          <stop offset="1" stopColor="#2337b3" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="url(#logo-bg)" />
      <path
        d="M10 7.5h8.5l4.5 4.5v12.5a1 1 0 0 1-1 1H10a1 1 0 0 1-1-1v-16a1 1 0 0 1 1-1Z"
        fill="#fff"
      />
      <path d="M18.5 7.5V11a1 1 0 0 0 1 1H23" fill="#c9d1ff" />
      <path
        d="m12.5 18.2 2.4 2.4 4.8-5"
        fill="none"
        stroke="#c8963e"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Logo({ className, light }: { className?: string; light?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark />
      <span
        className={cn(
          "text-[17px] font-semibold tracking-tight",
          light ? "text-sidebar-foreground" : "text-foreground",
        )}
      >
        TheContr
        <span className={light ? "text-[#9fb0ff]" : "text-primary"}>AI</span>
        ct
      </span>
    </span>
  );
}

const AVATAR_TONES = [
  "bg-[#e6ebff] text-[#2b3fbf] dark:bg-[#232c55] dark:text-[#b4c0ff]",
  "bg-[#f6ecd9] text-[#8a5a12] dark:bg-[#3b2f1a] dark:text-[#ecc98a]",
  "bg-[#e1f2e8] text-[#1d6b40] dark:bg-[#183526] dark:text-[#93dbb2]",
  "bg-[#f8e3e7] text-[#9b2c43] dark:bg-[#3e1f27] dark:text-[#f0a6b6]",
  "bg-[#e5eef6] text-[#2a587f] dark:bg-[#1d2f40] dark:text-[#a3c8ea]",
  "bg-[#efe6f6] text-[#5f3786] dark:bg-[#2e2240] dark:text-[#cfb0ec]",
];

/** Initials of a company or person on a soft tint that is stable for the same name. */
export function Avatar({ name, className }: { name: string | null; className?: string }) {
  const clean = (name ?? "?")
    .replace(/\b(ltd|limited|plc|gmbh|ag|inc|llc|sa|bv)\b\.?/gi, "")
    .trim();
  const initials =
    clean
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((w) => w[0]?.toUpperCase())
      .join("") || "?";
  let hash = 0;
  for (const ch of name ?? "") hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return (
    <span
      aria-hidden
      className={cn(
        "flex size-10 shrink-0 items-center justify-center rounded-xl text-sm font-semibold",
        AVATAR_TONES[hash % AVATAR_TONES.length],
        className,
      )}
    >
      {initials}
    </span>
  );
}
