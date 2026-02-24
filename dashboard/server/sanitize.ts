/**
 * Sanitization utilities for dashboard display.
 *
 * Port of src/atlasbridge/dashboard/sanitize.py to TypeScript.
 * Strips ANSI escape codes, redacts tokens/secrets, and truncates.
 */

// ANSI stripping — matches CSI, OSC, charset, and other ESC sequences
const ANSI_RE =
  /\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b[()][A-Z0-9]|\x1b[ -/]*[@-~]|\r/g;

export function stripAnsi(text: string): string {
  return text.replace(ANSI_RE, "");
}

// Token redaction patterns: [regex, replacement label]
const TOKEN_PATTERNS: [RegExp, string][] = [
  [/\b\d{8,10}:[A-Za-z0-9_-]{35,}\b/g, "[REDACTED:telegram-token]"],
  [/\bxox[bpsar]-[A-Za-z0-9-]{10,}\b/g, "[REDACTED:slack-token]"],
  [/\b(?:sk|ak|key)-[A-Za-z0-9]{20,}\b/g, "[REDACTED:api-key]"],
  [/\bgh[pousr]_[A-Za-z0-9]{36,}\b/g, "[REDACTED:github-pat]"],
  [/\bAKIA[A-Z0-9]{16}\b/g, "[REDACTED:aws-key]"],
  [/\b[0-9a-f]{64,}\b/g, "[REDACTED:hex-secret]"],
];

export function redactTokens(text: string): string {
  for (const [pattern, label] of TOKEN_PATTERNS) {
    text = text.replace(pattern, label);
  }
  return text;
}

const MAX_DISPLAY_LENGTH = 4096;

export function sanitizeForDisplay(
  text: string,
  maxLength = MAX_DISPLAY_LENGTH
): string {
  text = stripAnsi(text);
  text = redactTokens(text);
  if (text.length > maxLength) {
    text = text.slice(0, maxLength) + "\n... [truncated]";
  }
  return text;
}
