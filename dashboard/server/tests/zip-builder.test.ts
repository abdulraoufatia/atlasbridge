import { describe, it, expect, vi } from "vitest";
import { Writable, PassThrough } from "stream";
import type { Response } from "express";

function createMockResponse(): Response & { _headers: Record<string, string>; _data: Buffer[] } {
  const _headers: Record<string, string> = {};
  const _data: Buffer[] = [];

  const writable = new PassThrough();
  writable.on("data", (chunk) => _data.push(Buffer.from(chunk)));

  const res = writable as any;
  res._headers = _headers;
  res._data = _data;
  res.setHeader = (name: string, value: string) => { _headers[name] = value; };
  res.status = (code: number) => ({ end: () => {} });
  res.headersSent = false;

  return res;
}

describe("zip-builder", () => {
  it("streamZipResponse sets correct headers", async () => {
    const { streamZipResponse } = await import("../zip-builder");
    const res = createMockResponse();

    const entries = [
      { name: "test.txt", content: "hello world" },
      { name: "data.json", content: '{"key":"value"}' },
    ];

    streamZipResponse(res as any, "test-bundle.zip", entries);

    expect(res._headers["Content-Type"]).toBe("application/zip");
    expect(res._headers["Content-Disposition"]).toBe('attachment; filename="test-bundle.zip"');

    // Wait for archive to finalize
    await new Promise((resolve) => setTimeout(resolve, 200));
    const totalBytes = res._data.reduce((sum, buf) => sum + buf.length, 0);
    expect(totalBytes).toBeGreaterThan(0);
  });

  it("streamZipResponse handles empty entries", async () => {
    const { streamZipResponse } = await import("../zip-builder");
    const res = createMockResponse();

    streamZipResponse(res as any, "empty.zip", []);

    expect(res._headers["Content-Type"]).toBe("application/zip");

    await new Promise((resolve) => setTimeout(resolve, 200));
    // Even empty ZIPs have headers
    const totalBytes = res._data.reduce((sum, buf) => sum + buf.length, 0);
    expect(totalBytes).toBeGreaterThan(0);
  });

  it("streamZipResponse handles Buffer content", async () => {
    const { streamZipResponse } = await import("../zip-builder");
    const res = createMockResponse();

    const entries = [
      { name: "binary.bin", content: Buffer.from([0x00, 0x01, 0x02, 0xff]) },
    ];

    streamZipResponse(res as any, "binary.zip", entries);

    await new Promise((resolve) => setTimeout(resolve, 200));
    const totalBytes = res._data.reduce((sum, buf) => sum + buf.length, 0);
    expect(totalBytes).toBeGreaterThan(0);
  });

  it("streamZipFromDisk sets correct headers", async () => {
    const { streamZipFromDisk } = await import("../zip-builder");
    const res = createMockResponse();

    // Pass a non-existent file — archiver skips missing files gracefully
    streamZipFromDisk(res as any, "disk-bundle.zip", [
      { diskPath: "/nonexistent/file.txt", archiveName: "file.txt" },
    ]);

    expect(res._headers["Content-Type"]).toBe("application/zip");
    expect(res._headers["Content-Disposition"]).toBe('attachment; filename="disk-bundle.zip"');

    await new Promise((resolve) => setTimeout(resolve, 200));
  });

  it("streamZipResponse produces valid ZIP magic bytes", async () => {
    const { streamZipResponse } = await import("../zip-builder");
    const res = createMockResponse();

    streamZipResponse(res as any, "magic.zip", [
      { name: "hello.txt", content: "hello" },
    ]);

    await new Promise((resolve) => setTimeout(resolve, 300));
    const fullBuffer = Buffer.concat(res._data);
    // ZIP magic number: PK (0x50, 0x4B)
    expect(fullBuffer[0]).toBe(0x50);
    expect(fullBuffer[1]).toBe(0x4b);
  });
});
