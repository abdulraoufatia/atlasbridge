import type { Express } from "express";
import { execFile } from "child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { requireCsrf } from "../middleware/csrf";
import { operatorRateLimiter } from "../middleware/rate-limit";
import { insertOperatorAuditLog, queryOperatorAuditLog } from "../db";

// Resolve atlasbridge binary: env var > walk up from CWD looking for .venv > PATH.
function findAtlasBridgeBin(): string {
  if (process.env.ATLASBRIDGE_BIN) return process.env.ATLASBRIDGE_BIN;
  // Walk up from CWD until we find .venv/bin/atlasbridge (works from dashboard/ or repo root)
  let dir = process.cwd();
  for (let i = 0; i < 5; i++) {
    const candidate = path.join(dir, ".venv", "bin", "atlasbridge");
    if (existsSync(candidate)) return candidate;
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return "atlasbridge";
}

const ATLASBRIDGE_BIN = findAtlasBridgeBin();
const VALID_MODES = new Set(["off", "assist", "full"]);

// Exported for unit testing.
export function runAtlasBridge(args: string[]): Promise<{ stdout: string; stderr: string }> {
  // Strip CLAUDECODE so atlasbridge can spawn Claude Code even when the dashboard
  // itself was launched inside a Claude Code session.
  // Pass ATLASBRIDGE_BIN so nested atlasbridge invocations (e.g. sessions start → run)
  // can find the binary even when the venv is not on PATH.
  const env = { ...process.env };
  delete env.CLAUDECODE;
  env.ATLASBRIDGE_BIN = ATLASBRIDGE_BIN;

  return new Promise((resolve, reject) => {
    execFile(ATLASBRIDGE_BIN, args, { timeout: 10_000, env }, (err, stdout, stderr) => {
      if (err) {
        reject(Object.assign(err, { stdout, stderr }));
      } else {
        resolve({ stdout, stderr });
      }
    });
  });
}

export function registerOperatorRoutes(app: Express): void {
  // ---------------------------------------------------------------------------
  // Kill switch — disables autopilot immediately
  // ---------------------------------------------------------------------------
  app.post(
    "/api/operator/kill-switch",
    requireCsrf,
    operatorRateLimiter,
    async (req, res) => {
      const body = req.body as Record<string, unknown>;
      try {
        const { stdout } = await runAtlasBridge(["autopilot", "disable"]);
        insertOperatorAuditLog({
          method: "POST",
          path: "/api/operator/kill-switch",
          action: "kill-switch",
          body,
          result: "ok",
        });
        res.json({ ok: true, message: "Autopilot disabled", detail: stdout.trim() });
      } catch (err: any) {
        insertOperatorAuditLog({
          method: "POST",
          path: "/api/operator/kill-switch",
          action: "kill-switch",
          body,
          result: "error",
          error: err.message,
        });
        res.status(503).json({
          error: "Kill switch failed",
          detail: (err.stderr as string | undefined)?.trim() ?? err.message,
        });
      }
    },
  );

  // ---------------------------------------------------------------------------
  // Autonomy mode — set off / assist / full
  // ---------------------------------------------------------------------------
  app.post(
    "/api/operator/mode",
    requireCsrf,
    operatorRateLimiter,
    async (req, res) => {
      const body = req.body as Record<string, unknown>;
      const mode = (typeof body.mode === "string" ? body.mode : "").toLowerCase();

      if (!VALID_MODES.has(mode)) {
        res.status(400).json({ error: "Invalid mode. Must be: off, assist, full" });
        return;
      }

      try {
        const { stdout } = await runAtlasBridge(["autopilot", "mode", mode]);
        insertOperatorAuditLog({
          method: "POST",
          path: "/api/operator/mode",
          action: `set-mode:${mode}`,
          body,
          result: "ok",
        });
        res.json({ ok: true, mode, detail: stdout.trim() });
      } catch (err: any) {
        insertOperatorAuditLog({
          method: "POST",
          path: "/api/operator/mode",
          action: `set-mode:${mode}`,
          body,
          result: "error",
          error: err.message,
        });
        res.status(503).json({
          error: "Mode change failed",
          detail: (err.stderr as string | undefined)?.trim() ?? err.message,
        });
      }
    },
  );

  // ---------------------------------------------------------------------------
  // Operator audit log — read-only, no CSRF required
  // ---------------------------------------------------------------------------
  app.get("/api/operator/audit", (_req, res) => {
    res.json(queryOperatorAuditLog(100));
  });
}
