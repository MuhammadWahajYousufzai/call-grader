import { cookies } from "next/headers";
import { SESSION_COOKIE, authResponse, requireSameOrigin, sessionAccount } from "@/lib/auth";

export async function POST(request: Request) {
  try {
    requireSameOrigin(request);
    const jar = await cookies();
    const secret = jar.get(SESSION_COOKIE)?.value;
    if (secret) {
      try { await sessionAccount(secret).deleteSession({ sessionId: "current" }); } catch { /* Always clear the browser session. */ }
    }
    jar.delete(SESSION_COOKIE);
    return new Response(null, { status: 303, headers: { Location: "/login", "Cache-Control": "no-store" } });
  } catch (error) { return authResponse(error); }
}
