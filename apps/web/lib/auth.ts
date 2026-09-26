import "server-only";
import { Account, Client } from "node-appwrite";
import { cookies } from "next/headers";

export const SESSION_COOKIE = "call-grader-session";

export class AuthError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "AuthError";
  }
}

function client() {
  const endpoint = process.env.APPWRITE_SITE_API_ENDPOINT || process.env.APPWRITE_ENDPOINT || process.env.NEXT_PUBLIC_APPWRITE_ENDPOINT;
  const project = process.env.APPWRITE_SITE_PROJECT_ID || process.env.APPWRITE_PROJECT_ID || process.env.NEXT_PUBLIC_APPWRITE_PROJECT_ID;
  if (!endpoint || !project) throw new AuthError(503, "Sign-in is not configured.");
  return new Client().setEndpoint(endpoint).setProject(project);
}

export function sessionAccount(secret: string) {
  // A new session client per request, with no API key that bypasses permissions.
  return new Account(client().setSession(secret));
}

export function loginAccount(request?: Request) {
  const key = process.env.APPWRITE_AUTH_API_KEY || (process.env.APPWRITE_SITE_ID ? request?.headers.get("x-appwrite-key") : "");
  if (!key) throw new AuthError(503, "Sign-in is not configured.");
  return new Account(client().setKey(key));
}

export async function verifyAdmin(secret: string) {
  if (!secret) throw new AuthError(401, "Please sign in.");
  try {
    const account = sessionAccount(secret);
    // Fresh Appwrite response; never trust labels from a cookie, body or prefs.
    const user = await account.get();
    if (!user.status || !Array.isArray(user.labels) || !user.labels.includes("admin")) {
      throw new AuthError(403, "This account does not have admin access.");
    }
    if (user.mfa) {
      const session = await account.getSession({ sessionId: "current" });
      if (new Set(session.factors).size < 2) {
        throw new AuthError(401, "Additional Appwrite verification is required.");
      }
    }
    return user;
  } catch (error) {
    if (error instanceof AuthError) throw error;
    const code = (error as { code?: number }).code;
    if (code === 401 || code === 403) throw new AuthError(401, "Your session has expired. Please sign in.");
    throw new AuthError(503, "Appwrite is unavailable. Please try again shortly.");
  }
}

export async function requireAdmin() {
  return verifyAdmin((await cookies()).get(SESSION_COOKIE)?.value || "");
}

export function requireSameOrigin(request: Request) {
  const origin = request.headers.get("origin");
  if (!origin) throw new AuthError(403, "Request origin is not allowed.");
  const configured = process.env.APP_ORIGIN;
  if (configured) {
    if (origin !== configured) throw new AuthError(403, "Request origin is not allowed.");
    return;
  }
  // Next.js standalone request.url can use its internal bind address. The Host
  // header identifies the requested site, without trusting forwarded headers.
  let parsed: URL;
  try { parsed = new URL(origin); } catch { throw new AuthError(403, "Request origin is not allowed."); }
  const host = request.headers.get("host") || new URL(request.url).host;
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(parsed.hostname);
  if (parsed.host !== host || (!local && process.env.NODE_ENV === "production" && parsed.protocol !== "https:")) {
    throw new AuthError(403, "Request origin is not allowed.");
  }
}

export function authResponse(error: unknown) {
  const known = error instanceof AuthError;
  return Response.json(
    { error: known ? error.message : "Unable to complete sign-in. Please try again." },
    { status: known ? error.status : 503, headers: { "Cache-Control": "no-store" } },
  );
}
