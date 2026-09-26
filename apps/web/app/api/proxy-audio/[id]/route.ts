import { NextRequest, NextResponse } from "next/server";
import { authResponse, requireAdmin } from "@/lib/auth";

/** Authenticated audio proxy — streams private Appwrite file, no public URL. */
export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  let user;
  try { user = await requireAdmin(); } catch (error) { return authResponse(error); }
  const { id } = await params;
  const base = process.env.BACKEND_INTERNAL_URL || "http://localhost:8000";
  const headers: Record<string, string> = {};
  if (!process.env.INTERNAL_API_TOKEN) return NextResponse.json({ error: "Recording service unavailable" }, { status: 503 });
  headers["x-internal-token"] = process.env.INTERNAL_API_TOKEN;
  headers["x-actor"] = user.$id;
  if (!/^[a-zA-Z0-9._-]{1,36}$/.test(id)) return NextResponse.json({ error: "Invalid call" }, { status: 400 });
  const res = await fetch(`${base}/api/calls/${encodeURIComponent(id)}/audio`, { headers, cache: "no-store" });
  if (!res.ok) return NextResponse.json({ error: "recording unavailable" }, { status: 404 });
  return new NextResponse(res.body, { headers: { "Content-Type": res.headers.get("content-type") || "audio/wav", "Cache-Control": "private, no-store" } });
}
