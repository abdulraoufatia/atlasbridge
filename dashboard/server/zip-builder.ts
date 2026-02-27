/**
 * Streaming ZIP archive builder — wraps `archiver` for direct HTTP response streaming.
 */

import archiver from "archiver";
import fs from "fs";
import type { Response } from "express";

export function streamZipResponse(
  res: Response,
  filename: string,
  entries: { name: string; content: string | Buffer }[],
): void {
  res.setHeader("Content-Type", "application/zip");
  res.setHeader("Content-Disposition", `attachment; filename="${filename}"`);

  const archive = archiver("zip", { zlib: { level: 6 } });

  archive.on("error", (err) => {
    console.error("ZIP archive error:", err);
    if (!res.headersSent) res.status(500).end();
  });

  archive.pipe(res);

  for (const entry of entries) {
    archive.append(entry.content, { name: entry.name });
  }

  archive.finalize();
}

export function streamZipFromDisk(
  res: Response,
  filename: string,
  files: { diskPath: string; archiveName: string }[],
): void {
  res.setHeader("Content-Type", "application/zip");
  res.setHeader("Content-Disposition", `attachment; filename="${filename}"`);

  const archive = archiver("zip", { zlib: { level: 6 } });

  archive.on("error", (err) => {
    console.error("ZIP archive error:", err);
    if (!res.headersSent) res.status(500).end();
  });

  archive.pipe(res);

  for (const file of files) {
    if (fs.existsSync(file.diskPath)) {
      archive.file(file.diskPath, { name: file.archiveName });
    }
  }

  archive.finalize();
}
