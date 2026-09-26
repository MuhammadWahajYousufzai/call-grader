export function fmtTs(iso: string): string {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat("en-PK", {
      timeZone: "Asia/Karachi",
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function fmtClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds || 0));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export function scoreClass(score: number | null | undefined): string {
  if (score == null) return "bg-slate-200 text-slate-600";
  if (score >= 8) return "bg-emerald-100 text-emerald-800";
  if (score >= 6) return "bg-amber-100 text-amber-800";
  return "bg-red-100 text-red-800";
}
