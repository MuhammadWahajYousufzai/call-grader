import { NextRequest, NextResponse } from "next/server";
import { Storage } from "node-appwrite";
import { siteClient } from "@/lib/appwrite-server";
import { backendFetch } from "@/lib/backend";
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
  if (process.env.APPWRITE_BACKEND_FUNCTION_ID) {
    try {
      const detail = await backendFetch(`/api/calls/${encodeURIComponent(id)}`);
      const fileId = detail.call?.recording_storage_file_id;
      if (!detail.audio_available || !fileId) return NextResponse.json({ error: "recording unavailable" }, { status: 404 });
      const storage = new Storage(await siteClient());
      const bucketId = process.env.APPWRITE_RECORDINGS_BUCKET_ID || "call_recordings";
      const file = await storage.getFile({ bucketId, fileId });
      const audio = await storage.getFileDownload({ bucketId, fileId });
      return new NextResponse(audio, { headers: { "Content-Type": file.mimeType || "audio/wav", "Cache-Control": "private, no-store" } });
    } catch {
      return NextResponse.json({ error: "recording unavailable" }, { status: 503 });
    }
  }
  const res = await fetch(`${base}/api/calls/${encodeURIComponent(id)}/audio`, { headers, cache: "no-store" });
  if (!res.ok) return NextResponse.json({ error: "recording unavailable" }, { status: 404 });
  return new NextResponse(res.body, { headers: { "Content-Type": res.headers.get("content-type") || "audio/wav", "Cache-Control": "private, no-store" } });
}
