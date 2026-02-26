import type { Express } from "express";
import { execFile } from "child_process";
import { requireCsrf } from "../middleware/csrf";
import { operatorRateLimiter } from "../middleware/rate-limit";
import { insertOperatorAuditLog, queryOperatorAuditLog } from "../db";

// Allow test injection via env var; defaults to the atlasbridge CLI on PATH.
const ATLASBRIDGE_BIN = process.env.ATLASBRIDGE_BIN ?? "atlasbridge";
const VALID_MODES = new Set(["off", "assist", "full"]);

// Exported for unit testing.
export function runAtlasBridge(args: string[]): Promise<{ stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    execFile(ATLASBRIDGE_BIN, args, { timeout: 10_000 }, (err, stdout, stderr) => {
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
