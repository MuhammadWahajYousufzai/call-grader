import "server-only";
import { requireAdmin } from "./auth";
export { fmtTs, fmtClock, scoreClass } from "./format";

/** Server-only BFF: verify Appwrite admin access before fetching private data. */
export async function backendFetch(path: string, init: RequestInit = {}) {
  const user = await requireAdmin();
  const base = process.env.BACKEND_INTERNAL_URL || "http://localhost:8000";
  if (!process.env.INTERNAL_API_TOKEN) throw new Error("Backend access is not configured.");
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  headers.set("x-internal-token", process.env.INTERNAL_API_TOKEN);
  headers.set("x-actor", user.$id);
  const res = await fetch(`${base}${path}`, { ...init, headers, cache: "no-store" });
  if (!res.ok) throw new Error(`Backend request failed (${res.status}).`);
  return res.json();
}
