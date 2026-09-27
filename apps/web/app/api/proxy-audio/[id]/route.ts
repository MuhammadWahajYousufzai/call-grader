import { NextRequest, NextResponse } from "next/server";
import { Storage } from "node-appwrite";
import { siteClient } from "@/lib/appwrite-server";
import { backendFetch } from "@/lib/backend";
import { authResponse, requireAdmin } from "@/lib/auth";

/** Authenticated audio proxy — streams private Appwrite file, no public URL. */
export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try { await requireAdmin(); } catch (error) { return authResponse(error); }
  const { id } = await params;
  if (!/^[a-zA-Z0-9._-]{1,36}$/.test(id)) return NextResponse.json({ error: "Invalid call" }, { status: 400 });
  {
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
}
