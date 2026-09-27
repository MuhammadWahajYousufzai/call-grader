import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ admin: vi.fn(), execute: vi.fn(), client: vi.fn() }));
vi.mock("server-only", () => ({}));
vi.mock("./auth", () => ({ requireAdmin: mocks.admin }));
vi.mock("./appwrite-server", () => ({ siteClient: mocks.client }));
vi.mock("node-appwrite", () => ({ Functions: class { createExecution = mocks.execute; } }));
import { backendFetch } from "./backend";

afterEach(() => { vi.unstubAllEnvs(); vi.clearAllMocks(); });

describe("private Function backend", () => {
  it("rejects unauthorized callers before creating an execution", async () => {
    vi.stubEnv("APPWRITE_BACKEND_FUNCTION_ID", "api");
    mocks.admin.mockRejectedValueOnce(new Error("denied"));
    await expect(backendFetch("/api/reports")).rejects.toThrow("denied");
    expect(mocks.execute).not.toHaveBeenCalled();
  });
  it("passes the verified actor and handles unsuccessful Function responses", async () => {
    vi.stubEnv("APPWRITE_BACKEND_FUNCTION_ID", "api");
    vi.stubEnv("INTERNAL_API_TOKEN", "internal-test");
    mocks.admin.mockResolvedValue({ $id: "verified-admin" });
    mocks.execute.mockResolvedValueOnce({ status: "completed", responseStatusCode: 200, responseBody: '{"ok":true}' });
    expect(await backendFetch("/api/reports?date=2026-09-25")).toEqual({ ok: true });
    expect(mocks.execute).toHaveBeenCalledWith(expect.objectContaining({
      functionId: "api", async: false, xpath: "/api/reports?date=2026-09-25", method: "GET",
      headers: expect.objectContaining({ "x-actor": "verified-admin", "x-internal-token": "internal-test" }),
    }));
    mocks.execute.mockResolvedValueOnce({ status: "completed", responseStatusCode: 401, responseBody: '{}' });
    await expect(backendFetch("/api/reports")).rejects.toThrow("401");
  });
  it("fails closed if the Function id is missing", async () => {
    vi.stubEnv("APPWRITE_BACKEND_FUNCTION_ID", "");
    vi.stubEnv("INTERNAL_API_TOKEN", "internal-test");
    mocks.admin.mockResolvedValue({ $id: "verified-admin" });
    await expect(backendFetch("/api/reports")).rejects.toThrow("not configured");
    expect(mocks.execute).not.toHaveBeenCalled();
  });

});
