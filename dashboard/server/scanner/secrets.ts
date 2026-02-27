/**
 * Secret scanner — detects potential secrets in source files.
 * Only stores redacted fingerprints, never raw secret values.
 */

import fs from "fs";
import path from "path";
import { createHash } from "crypto";
import { execFileSync } from "child_process";
import type { SecretFinding } from "@shared/schema";
import { SECRET_PATTERNS, SKIP_DIRS, BINARY_EXTENSIONS } from "./patterns";

const MAX_FILE_SIZE = 1024 * 1024; // 1MB
const MAX_LINE_LENGTH = 2000;

function fingerprint(value: string): string {
  return createHash("sha256").update(value).digest("hex").slice(0, 12);
}

function isBinaryFile(filePath: string): boolean {
  const ext = path.extname(filePath).toLowerCase();
  return BINARY_EXTENSIONS.has(ext);
}

function shouldSkipPath(relativePath: string): boolean {
  const parts = relativePath.split(path.sep);
  return parts.some((p) => SKIP_DIRS.has(p));
}

function listGitFiles(repoPath: string): string[] {
  try {
    const output = execFileSync("git", ["ls-files"], {
      cwd: repoPath,
      timeout: 15_000,
      encoding: "utf-8",
      maxBuffer: 10 * 1024 * 1024,
    });
    return output.split("\n").filter((l) => l.trim());
  } catch {
    return [];
  }
}

export function scanForSecrets(repoPath: string): SecretFinding[] {
  const findings: SecretFinding[] = [];
  const files = listGitFiles(repoPath);

  for (const file of files) {
    if (shouldSkipPath(file)) continue;
    if (isBinaryFile(file)) continue;

    const fullPath = path.join(repoPath, file);

    // Check file size
    let stat: fs.Stats;
    try {
      stat = fs.statSync(fullPath);
    } catch {
      continue;
    }
    if (stat.size > MAX_FILE_SIZE) continue;
    if (!stat.isFile()) continue;

    // Read file
    let content: string;
    try {
      content = fs.readFileSync(fullPath, "utf-8");
    } catch {
      continue;
    }

    const lines = content.split("\n");
    for (let lineIdx = 0; lineIdx < lines.length; lineIdx++) {
      const line = lines[lineIdx];
      if (line.length > MAX_LINE_LENGTH) continue;

      // Skip comment-only lines that look like documentation
      const trimmed = line.trim();
      if (trimmed.startsWith("//") && trimmed.includes("example")) continue;
      if (trimmed.startsWith("#") && trimmed.includes("example")) continue;

      for (const { name, pattern } of SECRET_PATTERNS) {
        // Reset regex lastIndex since patterns use /g flag
        pattern.lastIndex = 0;
        let match: RegExpExecArray | null;
        while ((match = pattern.exec(line)) !== null) {
          const matchValue = match[0];

          // Skip very short matches (likely false positives)
          if (matchValue.length < 8) continue;

          // Skip matches that are clearly placeholder/example values
          if (/^(example|test|demo|placeholder|xxx|your[-_])/i.test(matchValue)) continue;
          if (/password\s*=\s*["']?$/i.test(matchValue)) continue;

          findings.push({
            file,
            line: lineIdx + 1,
            type: name,
            fingerprint: fingerprint(matchValue),
          });

          // Only report first match per pattern per line
          break;
        }
      }
    }
  }

  return findings;
}
