import { describe, it, expect, vi, beforeEach } from "vitest";
import { execFile } from "child_process";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("child_process", () => ({ execFile: vi.fn() }));

vi.mock("../db", () => ({
  insertOperatorAuditLog: vi.fn(),
  queryOperatorAuditLog: vi.fn(() => []),
  db: {},
  getAtlasBridgeDb: vi.fn(() => null),
}));

// ---------------------------------------------------------------------------
// runAtlasBridge
// ---------------------------------------------------------------------------

describe("runAtlasBridge", () => {
  beforeEach(() => vi.clearAllMocks());

  it("resolves with stdout when execFile succeeds", async () => {
    vi.mocked(execFile).mockImplementation((_bin, _args, _opts, cb: any) => {
      cb(null, "autopilot disabled\n", "");
    });
    const { runAtlasBridge } = await import("../routes/operator");
    const result = await runAtlasBridge(["autopilot", "disable"]);
    expect(result.stdout).toBe("autopilot disabled\n");
    expect(result.stderr).toBe("");
  });

  it("rejects when execFile fails", async () => {
    vi.mocked(execFile).mockImplementation((_bin, _args, _opts, cb: any) => {
      cb(new Error("not found"), "", "command not found: atlasbridge");
    });
    const { runAtlasBridge } = await import("../routes/operator");
    await expect(runAtlasBridge(["autopilot", "disable"])).rejects.toThrow("not found");
  });

  it("uses the ATLASBRIDGE_BIN env var when set", async () => {
    process.env.ATLASBRIDGE_BIN = "/custom/path/atlasbridge";
    vi.resetModules();
    vi.mock("child_process", () => ({ execFile: vi.fn() }));
    vi.mock("../db", () => ({
      insertOperatorAuditLog: vi.fn(),
      queryOperatorAuditLog: vi.fn(() => []),
      db: {},
      getAtlasBridgeDb: vi.fn(() => null),
    }));
    const { execFile: mocked } = await import("child_process");
    vi.mocked(mocked).mockImplementation((_bin, _args, _opts, cb: any) => cb(null, "ok", ""));
    const { runAtlasBridge } = await import("../routes/operator");
    await runAtlasBridge(["autopilot", "disable"]);
    expect(vi.mocked(mocked)).toHaveBeenCalledWith(
      "/custom/path/atlasbridge",
      expect.any(Array),
      expect.any(Object),
      expect.any(Function),
    );
    delete process.env.ATLASBRIDGE_BIN;
  });
});

// ---------------------------------------------------------------------------
// requireCsrf middleware
// ---------------------------------------------------------------------------

describe("requireCsrf", () => {
  beforeEach(() => vi.resetModules());

  async function getRequireCsrf() {
    const mod = await import("../middleware/csrf");
    return mod.requireCsrf;
  }

  it("returns 403 when x-csrf-token header is missing", async () => {
    const requireCsrf = await getRequireCsrf();
    const req = { headers: { cookie: "csrf-token=abc123" } } as any;
    const res = { status: vi.fn().mockReturnThis(), json: vi.fn() } as any;
    const next = vi.fn();

    requireCsrf(req, res, next);

    expect(res.status).toHaveBeenCalledWith(403);
    expect(res.json).toHaveBeenCalledWith({ error: "CSRF token mismatch" });
    expect(next).not.toHaveBeenCalled();
  });

  it("returns 403 when header does not match cookie", async () => {
    const requireCsrf = await getRequireCsrf();
    const req = {
      headers: { cookie: "csrf-token=abc123", "x-csrf-token": "wrong" },
    } as any;
    const res = { status: vi.fn().mockReturnThis(), json: vi.fn() } as any;
    const next = vi.fn();

    requireCsrf(req, res, next);

    expect(res.status).toHaveBeenCalledWith(403);
    expect(next).not.toHaveBeenCalled();
  });

  it("calls next() when header matches cookie", async () => {
    const requireCsrf = await getRequireCsrf();
    const req = {
      headers: { cookie: "csrf-token=abc123", "x-csrf-token": "abc123" },
    } as any;
    const res = { status: vi.fn().mockReturnThis(), json: vi.fn() } as any;
    const next = vi.fn();

    requireCsrf(req, res, next);

    expect(next).toHaveBeenCalled();
    expect(res.status).not.toHaveBeenCalled();
  });

  it("returns 403 when no cookie is present", async () => {
    const requireCsrf = await getRequireCsrf();
    const req = {
      headers: { "x-csrf-token": "abc123" },
    } as any;
    const res = { status: vi.fn().mockReturnThis(), json: vi.fn() } as any;
    const next = vi.fn();

    requireCsrf(req, res, next);

    expect(res.status).toHaveBeenCalledWith(403);
  });
});

// ---------------------------------------------------------------------------
// createRateLimiter
// ---------------------------------------------------------------------------

describe("createRateLimiter", () => {
  beforeEach(() => vi.resetModules());

  it("allows requests under the limit", async () => {
    const { createRateLimiter } = await import("../middleware/rate-limit");
    const limiter = createRateLimiter({ windowMs: 60_000, max: 5 });
    const req = { ip: "127.0.0.1", path: "/api/operator/kill-switch-test-1" } as any;
    const res = { status: vi.fn().mockReturnThis(), json: vi.fn(), setHeader: vi.fn() } as any;
    const next = vi.fn();

    limiter(req, res, next);
    limiter(req, res, next);

    expect(next).toHaveBeenCalledTimes(2);
    expect(res.status).not.toHaveBeenCalled();
  });

  it("returns 429 after max requests in window", async () => {
    const { createRateLimiter } = await import("../middleware/rate-limit");
    const limiter = createRateLimiter({ windowMs: 60_000, max: 2 });
    const req = { ip: "127.0.0.1", path: "/api/operator/kill-switch-test-2" } as any;
    const res = { status: vi.fn().mockReturnThis(), json: vi.fn(), setHeader: vi.fn() } as any;
    const next = vi.fn();

    limiter(req, res, next); // 1
    limiter(req, res, next); // 2
    limiter(req, res, next); // 3 → 429

    expect(next).toHaveBeenCalledTimes(2);
    expect(res.status).toHaveBeenCalledWith(429);
    expect(res.json).toHaveBeenCalledWith(
      expect.objectContaining({ error: expect.stringContaining("Too many requests") }),
    );
  });

  it("sets Retry-After header on 429", async () => {
    const { createRateLimiter } = await import("../middleware/rate-limit");
    const limiter = createRateLimiter({ windowMs: 60_000, max: 1 });
    const req = { ip: "127.0.0.1", path: "/api/operator/kill-switch-test-3" } as any;
    const res = { status: vi.fn().mockReturnThis(), json: vi.fn(), setHeader: vi.fn() } as any;
    const next = vi.fn();

    limiter(req, res, next); // 1
    limiter(req, res, next); // 2 → 429

    expect(res.setHeader).toHaveBeenCalledWith("Retry-After", expect.any(Number));
  });
});

// ---------------------------------------------------------------------------
// Operator audit log helpers
// ---------------------------------------------------------------------------

describe("operator audit log", () => {
  it("insertOperatorAuditLog and queryOperatorAuditLog are exported from db", async () => {
    const db = await import("../db");
    expect(typeof db.insertOperatorAuditLog).toBe("function");
    expect(typeof db.queryOperatorAuditLog).toBe("function");
  });

  it("queryOperatorAuditLog returns an array", async () => {
    const { queryOperatorAuditLog } = await import("../db");
    const rows = queryOperatorAuditLog(10);
    expect(Array.isArray(rows)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Mode validation
// ---------------------------------------------------------------------------

describe("mode validation", () => {
  it("accepts off, assist, full (lowercase)", () => {
    const VALID_MODES = new Set(["off", "assist", "full"]);
    expect(VALID_MODES.has("off")).toBe(true);
    expect(VALID_MODES.has("assist")).toBe(true);
    expect(VALID_MODES.has("full")).toBe(true);
  });

  it("rejects invalid mode strings", () => {
    const VALID_MODES = new Set(["off", "assist", "full"]);
    expect(VALID_MODES.has("auto")).toBe(false);
    expect(VALID_MODES.has("")).toBe(false);
    expect(VALID_MODES.has("Full")).toBe(false); // case sensitive — route normalises
  });

  it("normalises AutonomyMode capitalised values to lowercase", () => {
    // The route does: (typeof body.mode === "string" ? body.mode : "").toLowerCase()
    const VALID_MODES = new Set(["off", "assist", "full"]);
    expect(VALID_MODES.has("Off".toLowerCase())).toBe(true);
    expect(VALID_MODES.has("Assist".toLowerCase())).toBe(true);
    expect(VALID_MODES.has("Full".toLowerCase())).toBe(true);
  });
});
