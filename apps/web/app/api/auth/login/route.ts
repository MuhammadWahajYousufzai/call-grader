import { cookies } from "next/headers";
import { AuthError, SESSION_COOKIE, authResponse, loginAccount, requireSameOrigin, sessionAccount, verifyAdmin } from "@/lib/auth";

export async function POST(request: Request) {
  let secret = "";
  try {
    requireSameOrigin(request);
    const { email, password } = await request.json();
    if (typeof email !== "string" || typeof password !== "string" || !email.trim() || !password || email.length > 320 || password.length > 1024) {
      throw new AuthError(400, "Enter your email and password.");
    }
    let session;
    try {
      session = await loginAccount(request).createEmailPasswordSession({ email: email.trim(), password });
    } catch (error) {
      if ((error as { code?: number }).code === 401) throw new AuthError(401, "Email or password is incorrect.");
      throw error;
    }
    secret = session.secret;
    if (!secret) throw new AuthError(503, "Sign-in is not configured.");
    await verifyAdmin(secret);
    (await cookies()).set(SESSION_COOKIE, secret, {
      httpOnly: true, secure: process.env.NODE_ENV === "production",
      sameSite: "strict", path: "/", expires: new Date(session.expire),
    });
    return Response.json({ ok: true }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    if (secret) {
      try { await sessionAccount(secret).deleteSession({ sessionId: "current" }); } catch { /* Fail closed even during an outage. */ }
    }
    return authResponse(error);
  }
}
