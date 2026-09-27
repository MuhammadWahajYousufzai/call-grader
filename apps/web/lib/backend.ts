import "server-only";
import { requireAdmin } from "./auth";
import { Functions, ExecutionMethod } from "node-appwrite";
import { siteClient } from "./appwrite-server";
export { fmtTs, fmtClock, scoreClass } from "./format";

/** Server-only BFF: verify Appwrite admin access before fetching private data. */
export async function backendFetch(path: string, init: RequestInit = {}) {
  const user = await requireAdmin();
  if (!process.env.APPWRITE_BACKEND_FUNCTION_ID || !process.env.INTERNAL_API_TOKEN) throw new Error("Backend access is not configured.");
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  headers.set("x-internal-token", process.env.INTERNAL_API_TOKEN);
  headers.set("x-actor", user.$id);
    const execution = await new Functions(await siteClient()).createExecution({
      functionId: process.env.APPWRITE_BACKEND_FUNCTION_ID,
      async: false,
      xpath: path,
      method: (init.method || "GET") as ExecutionMethod,
      body: typeof init.body === "string" ? init.body : "",
      headers: Object.fromEntries(headers.entries()),
    });
    if (execution.status !== "completed" || execution.responseStatusCode < 200 || execution.responseStatusCode >= 300) {
      throw new Error(`Backend request failed (${execution.responseStatusCode || 503}).`);
    }
    return JSON.parse(execution.responseBody);
}
