import "server-only";
import { Client } from "node-appwrite";
import { headers } from "next/headers";

/** Scoped Site execution credentials; callers must verify admin first. */
export async function siteClient() {
  const endpoint = process.env.APPWRITE_ENDPOINT || process.env.APPWRITE_SITE_API_ENDPOINT;
  const project = process.env.APPWRITE_SITE_PROJECT_ID || process.env.APPWRITE_PROJECT_ID;
  const key = process.env.APPWRITE_SITE_ID ? (await headers()).get("x-appwrite-key") : process.env.APPWRITE_SERVER_API_KEY;
  if (!endpoint || !project || !key) throw new Error("Appwrite Site service is not configured.");
  return new Client().setEndpoint(endpoint).setProject(project).setKey(key);
}
