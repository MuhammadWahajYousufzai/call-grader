import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  get: vi.fn(), getSession: vi.fn(), createSession: vi.fn(), deleteSession: vi.fn(),
  cookieGet: vi.fn(), cookieSet: vi.fn(), cookieDelete: vi.fn(), fetch: vi.fn(), execute: vi.fn(),
}));
vi.mock("server-only", () => ({}));
vi.mock("next/headers", () => ({ cookies: async () => ({ get: mocks.cookieGet, set: mocks.cookieSet, delete: mocks.cookieDelete }) }));
vi.mock("./appwrite-server", () => ({ siteClient: async () => ({}) }));
vi.mock("node-appwrite", () => ({
  Functions: class { createExecution = mocks.execute; },
  Client: class { setEndpoint() { return this; } setProject() { return this; } setKey() { return this; } setSession() { return this; } },
  Account: class { get = mocks.get; getSession = mocks.getSession; createEmailPasswordSession = mocks.createSession; deleteSession = mocks.deleteSession; },
}));

import { requireAdmin, verifyAdmin, requireSameOrigin } from "./auth";
import { backendFetch } from "./backend";
import { POST as login } from "../app/api/auth/login/route";
import { POST as logout } from "../app/api/auth/logout/route";
import { GET as audio } from "../app/api/proxy-audio/[id]/route";

const admin = { $id: "verified-admin", status: true, labels: ["admin"], mfa: false };
const request = (origin = "https://dashboard.example") => new Request("https://dashboard.example/api/auth/login", {
  method: "POST", headers: { origin, "Content-Type": "application/json" },
  body: JSON.stringify({ email: "test@example.invalid", password: "test-only", labels: ["admin"] }),
});

beforeEach(() => {
  vi.resetAllMocks();
  vi.stubEnv("APPWRITE_ENDPOINT", "https://appwrite.example/v1");
  vi.stubEnv("APPWRITE_PROJECT_ID", "test-project");
  vi.stubEnv("APPWRITE_AUTH_API_KEY", "test-auth-key");
  vi.stubEnv("APPWRITE_BACKEND_FUNCTION_ID", "api");
  vi.stubEnv("INTERNAL_API_TOKEN", "test-internal-token");
  vi.stubEnv("APP_ORIGIN", "https://dashboard.example");
  vi.stubEnv("NODE_ENV", "production");
  vi.stubGlobal("fetch", mocks.fetch);
  mocks.cookieGet.mockReturnValue({ value: "test-session" });
  mocks.get.mockResolvedValue(admin);
  mocks.createSession.mockResolvedValue({ secret: "test-session", expire: "2027-01-01T00:00:00.000Z" });
  mocks.deleteSession.mockResolvedValue({});
});

describe("server-side admin authorization", () => {
  it("denies missing sessions before contacting Appwrite or the backend", async () => {
    mocks.cookieGet.mockReturnValue(undefined);
    await expect(backendFetch("/api/dashboard")).rejects.toMatchObject({ status: 401 });
    expect(mocks.get).not.toHaveBeenCalled(); expect(mocks.fetch).not.toHaveBeenCalled();
  });
  it("denies a non-admin even when preferences claim admin", async () => {
    mocks.get.mockResolvedValue({ ...admin, labels: [], prefs: { labels: ["admin"], role: "admin" } });
    await expect(backendFetch("/api/dashboard")).rejects.toMatchObject({ status: 403 });
    expect(mocks.fetch).not.toHaveBeenCalled();
  });
  it("rechecks labels and denies access immediately after admin is removed", async () => {
    await expect(requireAdmin()).resolves.toMatchObject(admin);
    mocks.get.mockResolvedValue({ ...admin, labels: [] });
    await expect(requireAdmin()).rejects.toMatchObject({ status: 403 });
    expect(mocks.get).toHaveBeenCalledTimes(2);
  });
  it("rejects revoked sessions and Appwrite outages", async () => {
    mocks.get.mockRejectedValue({ code: 401 });
    await expect(requireAdmin()).rejects.toMatchObject({ status: 401 });
    mocks.get.mockRejectedValue(new Error("connection lost"));
    await expect(requireAdmin()).rejects.toMatchObject({ status: 503 });
  });
  it("rejects disabled accounts and incomplete MFA", async () => {
    mocks.get.mockResolvedValue({ ...admin, status: false });
    await expect(requireAdmin()).rejects.toMatchObject({ status: 403 });
    mocks.get.mockResolvedValue({ ...admin, mfa: true });
    mocks.getSession.mockResolvedValue({ factors: ["password"] });
    await expect(verifyAdmin("test-session")).rejects.toMatchObject({ status: 401 });
    mocks.getSession.mockResolvedValue({ factors: ["password", "totp"] });
    await expect(requireAdmin()).resolves.toHaveProperty("labels", ["admin"]);
  });
  it("forwards the verified identity and overwrites spoofed internal headers", async () => {
    mocks.execute.mockResolvedValue({ status: "completed", responseStatusCode: 200, responseBody: '{"ok":true}' });
    await backendFetch("/api/admin/agents", { method: "POST", headers: { "x-actor": "spoofed", "x-internal-token": "spoofed" } });
    const options = mocks.execute.mock.calls[0][0];
    expect(options.headers["x-actor"]).toBe(admin.$id);
    expect(options.headers["x-internal-token"]).toBe("test-internal-token");
  });
  it("denies audio access without contacting the recording backend", async () => {
    mocks.get.mockResolvedValue({ ...admin, labels: [] });
    const response = await audio({} as never, { params: Promise.resolve({ id: "test-call" }) });
    expect(response.status).toBe(403); expect(mocks.fetch).not.toHaveBeenCalled();
  });
});

describe("sign-in and sign-out", () => {
  it("stores an admin session only in an HTTP-only secure cookie", async () => {
    const response = await login(request());
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ ok: true });
    expect(mocks.cookieSet).toHaveBeenCalledWith("call-grader-session", "test-session", expect.objectContaining({ httpOnly: true, secure: true, sameSite: "strict", path: "/" }));
  });
  it("rejects a forged admin body and removes the non-admin session", async () => {
    mocks.get.mockResolvedValue({ ...admin, labels: [] });
    expect((await login(request())).status).toBe(403);
    expect(mocks.cookieSet).not.toHaveBeenCalled(); expect(mocks.deleteSession).toHaveBeenCalled();
  });
  it("rejects cross-origin login and logout before processing credentials", async () => {
    expect((await login(request("https://other.example"))).status).toBe(403);
    expect((await logout(request("https://other.example"))).status).toBe(403);
    expect(mocks.createSession).not.toHaveBeenCalled(); expect(mocks.cookieDelete).not.toHaveBeenCalled();
    expect(() => requireSameOrigin(new Request("https://dashboard.example/api/auth/login"))).toThrow();
  });
  it("validates the public Host when a standalone server has an internal bind URL", () => {
    vi.stubEnv("APP_ORIGIN", "");
    const valid = new Request("http://0.0.0.0:3000/api/auth/login", { headers: { host: "dashboard.example", origin: "https://dashboard.example" } });
    expect(() => requireSameOrigin(valid)).not.toThrow();
    const forged = new Request("http://0.0.0.0:3000/api/auth/login", { headers: { host: "dashboard.example", origin: "https://other.example", "x-forwarded-host": "other.example" } });
    expect(() => requireSameOrigin(forged)).toThrow();
  });
  it("accepts local Appwrite Site origins and rejects HTTP production origins", () => {
    vi.stubEnv("APP_ORIGIN", "");
    const local = new Request("http://site.sites.localhost/api/auth/login", { headers: { host: "site.sites.localhost", origin: "http://site.sites.localhost" } });
    expect(() => requireSameOrigin(local)).not.toThrow();
    const insecure = new Request("http://dashboard.example/api/auth/login", { headers: { host: "dashboard.example", origin: "http://dashboard.example" } });
    expect(() => requireSameOrigin(insecure)).toThrow();
  });
  it("fails closed without an authentication key", async () => {
    vi.stubEnv("APPWRITE_AUTH_API_KEY", "");
    expect((await login(request())).status).toBe(503);
    expect(mocks.cookieSet).not.toHaveBeenCalled();
  });
  it("revokes the session and clears the cookie on sign-out", async () => {
    const response = await logout(request());
    expect(response.status).toBe(303); expect(response.headers.get("location")).toBe("/login");
    expect(mocks.deleteSession).toHaveBeenCalled();
    expect(mocks.cookieDelete).toHaveBeenCalledWith("call-grader-session");
  });
});
