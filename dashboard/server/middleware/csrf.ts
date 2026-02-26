import type { Request, Response, NextFunction } from "express";
import crypto from "crypto";

const TOKEN_COOKIE = "csrf-token";
const TOKEN_HEADER = "x-csrf-token";

// Set a CSRF token cookie on every response if one isn't already present.
// httpOnly: false is intentional — the JS client must read it from document.cookie.
export function setCsrfCookie(req: Request, res: Response, next: NextFunction): void {
  if (!req.headers.cookie?.includes(TOKEN_COOKIE)) {
    const token = crypto.randomBytes(16).toString("hex");
    res.cookie(TOKEN_COOKIE, token, {
      httpOnly: false,
      sameSite: "strict",
      path: "/",
    });
  }
  next();
}

// Validate that the x-csrf-token header matches the csrf-token cookie.
export function requireCsrf(req: Request, res: Response, next: NextFunction): void {
  const cookieHeader = req.headers.cookie ?? "";
  const match = cookieHeader.match(new RegExp(`(?:^|;\\s*)${TOKEN_COOKIE}=([^;]+)`));
  const cookieToken = match?.[1];
  const headerToken = req.headers[TOKEN_HEADER];

  if (!cookieToken || cookieToken !== headerToken) {
    res.status(403).json({ error: "CSRF token mismatch" });
    return;
  }
  next();
}
