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
// Session pause via runAtlasBridge
// ---------------------------------------------------------------------------

describe("session pause/resume/stop via runAtlasBridge", () => {
  beforeEach(() => vi.clearAllMocks());

  it("pause resolves with SIGSTOP JSON on success", async () => {
    vi.mocked(execFile).mockImplementation((_bin, _args, _opts, cb: any) => {
      cb(null, '{"ok":true,"session_id":"abc123","pid":1234,"signal":"SIGSTOP"}\n', "");
    });
    const { runAtlasBridge } = await import("../routes/operator");
    const result = await runAtlasBridge(["sessions", "pause", "abc123", "--json"]);
    const parsed = JSON.parse(result.stdout.trim());
    expect(parsed.ok).toBe(true);
    expect(parsed.signal).toBe("SIGSTOP");
  });

  it("resume resolves with SIGCONT JSON on success", async () => {
    vi.mocked(execFile).mockImplementation((_bin, _args, _opts, cb: any) => {
      cb(null, '{"ok":true,"session_id":"abc123","pid":1234,"signal":"SIGCONT"}\n', "");
    });
    const { runAtlasBridge } = await import("../routes/operator");
    const result = await runAtlasBridge(["sessions", "resume", "abc123", "--json"]);
    const parsed = JSON.parse(result.stdout.trim());
    expect(parsed.ok).toBe(true);
    expect(parsed.signal).toBe("SIGCONT");
  });

  it("stop resolves with SIGTERM JSON on success", async () => {
    vi.mocked(execFile).mockImplementation((_bin, _args, _opts, cb: any) => {
      cb(null, '{"ok":true,"session_id":"abc123","pid":1234,"signal":"SIGTERM"}\n', "");
    });
    const { runAtlasBridge } = await import("../routes/operator");
    const result = await runAtlasBridge(["sessions", "stop", "abc123", "--json"]);
    const parsed = JSON.parse(result.stdout.trim());
    expect(parsed.ok).toBe(true);
    expect(parsed.signal).toBe("SIGTERM");
  });

  it("rejects when pause command fails", async () => {
    vi.mocked(execFile).mockImplementation((_bin, _args, _opts, cb: any) => {
      const err = new Error("exit code 1");
      Object.assign(err, { stdout: '{"ok":false,"error":"No PID"}', stderr: "" });
      cb(err, "", "");
    });
    const { runAtlasBridge } = await import("../routes/operator");
    await expect(runAtlasBridge(["sessions", "pause", "abc123", "--json"])).rejects.toThrow();
  });

  it("rejects when resume command fails", async () => {
    vi.mocked(execFile).mockImplementation((_bin, _args, _opts, cb: any) => {
      const err = new Error("exit code 1");
      Object.assign(err, { stdout: '{"ok":false,"error":"not paused"}', stderr: "" });
      cb(err, "", "");
    });
    const { runAtlasBridge } = await import("../routes/operator");
    await expect(runAtlasBridge(["sessions", "resume", "abc123", "--json"])).rejects.toThrow();
  });
});

// ---------------------------------------------------------------------------
// Session start dedup guard
// ---------------------------------------------------------------------------

describe("session start dedup guard", () => {
  it("prevents rapid duplicate starts within 3s window", () => {
    // Simulate the server-side dedup logic
    let lastStart = 0;

    function canStart(): boolean {
      if (lastStart && Date.now() - lastStart < 3000) {
        return false;
      }
      lastStart = Date.now();
      return true;
    }

    expect(canStart()).toBe(true);
    expect(canStart()).toBe(false); // within 3s
  });

  it("allows start after 3s window passes", () => {
    let lastStart = Date.now() - 4000; // 4 seconds ago

    function canStart(): boolean {
      if (lastStart && Date.now() - lastStart < 3000) {
        return false;
      }
      lastStart = Date.now();
      return true;
    }

    expect(canStart()).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Custom adapter validation
// ---------------------------------------------------------------------------

describe("custom adapter validation", () => {
  it("accepts custom as valid adapter", () => {
    const VALID_ADAPTERS = new Set(["claude", "openai", "gemini", "claude-code", "custom"]);
    expect(VALID_ADAPTERS.has("custom")).toBe(true);
  });

  it("requires customCommand when adapter is custom", () => {
    const adapter = "custom";
    const customCommand = "";
    const isValid = adapter !== "custom" || customCommand.trim().length > 0;
    expect(isValid).toBe(false);
  });

  it("passes when customCommand is provided for custom adapter", () => {
    const adapter = "custom";
    const customCommand = "cursor";
    const isValid = adapter !== "custom" || customCommand.trim().length > 0;
    expect(isValid).toBe(true);
  });

  it("does not require customCommand for non-custom adapters", () => {
    const adapter = "claude";
    const customCommand = "";
    const isValid = adapter !== "custom" || customCommand.trim().length > 0;
    expect(isValid).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Session status mapping
// ---------------------------------------------------------------------------

describe("session status mapping", () => {
  function mapSessionStatus(status: string): "running" | "stopped" | "paused" {
    switch (status) {
      case "starting":
      case "running":
        return "running";
      case "paused":
        return "paused";
      default:
        return "stopped";
    }
  }

  it("maps 'running' to 'running'", () => {
    expect(mapSessionStatus("running")).toBe("running");
  });

  it("maps 'starting' to 'running'", () => {
    expect(mapSessionStatus("starting")).toBe("running");
  });

  it("maps 'paused' to 'paused'", () => {
    expect(mapSessionStatus("paused")).toBe("paused");
  });

  it("maps 'completed' to 'stopped'", () => {
    expect(mapSessionStatus("completed")).toBe("stopped");
  });

  it("maps 'canceled' to 'stopped'", () => {
    expect(mapSessionStatus("canceled")).toBe("stopped");
  });

  it("maps 'crashed' to 'stopped'", () => {
    expect(mapSessionStatus("crashed")).toBe("stopped");
  });

  it("maps unknown status to 'stopped'", () => {
    expect(mapSessionStatus("unknown")).toBe("stopped");
  });
});
