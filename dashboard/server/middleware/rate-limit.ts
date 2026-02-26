import type { Request, Response, NextFunction } from "express";

interface RateWindow {
  count: number;
  windowStart: number;
}

// In-memory sliding window counter. At localhost scale with a 60s window
// this is not a memory concern; no eviction is needed.
const windows = new Map<string, RateWindow>();

export function createRateLimiter(opts: { windowMs: number; max: number }) {
  return (req: Request, res: Response, next: NextFunction): void => {
    const key = `${req.ip}:${req.path}`;
    const now = Date.now();
    const win = windows.get(key);

    if (!win || now - win.windowStart > opts.windowMs) {
      windows.set(key, { count: 1, windowStart: now });
      next();
      return;
    }

    if (win.count >= opts.max) {
      const retryAfter = Math.ceil((opts.windowMs - (now - win.windowStart)) / 1000);
      res.setHeader("Retry-After", retryAfter);
      res.status(429).json({ error: "Too many requests. Try again shortly." });
      return;
    }

    win.count += 1;
    next();
  };
}

// 10 operator actions per minute per IP+path
export const operatorRateLimiter = createRateLimiter({ windowMs: 60_000, max: 10 });
