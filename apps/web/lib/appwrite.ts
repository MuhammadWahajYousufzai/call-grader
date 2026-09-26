import { Client, Account } from "appwrite";

export function appwriteClient() {
  const client = new Client()
    .setEndpoint(process.env.NEXT_PUBLIC_APPWRITE_ENDPOINT || "http://localhost/v1")
    .setProject(process.env.NEXT_PUBLIC_APPWRITE_PROJECT_ID || "");
  return client;
}

export function account() {
  return new Account(appwriteClient());
}
