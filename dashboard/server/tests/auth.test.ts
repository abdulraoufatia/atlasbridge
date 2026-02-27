import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import fs from "fs";
import os from "os";
import path from "path";
import { createSign, generateKeyPairSync } from "crypto";

// ---------------------------------------------------------------------------
// GitHub App — JWT generation
// ---------------------------------------------------------------------------
describe("GitHub App auth", () => {
  let testKeyDir: string;
  let privateKeyPath: string;
  let privateKeyPem: string;

  beforeEach(() => {
    testKeyDir = fs.mkdtempSync(path.join(os.tmpdir(), "auth-test-"));
    // Generate a real RSA key pair for testing
    const { privateKey } = generateKeyPairSync("rsa", {
      modulusLength: 2048,
      publicKeyEncoding: { type: "spki", format: "pem" },
      privateKeyEncoding: { type: "pkcs8", format: "pem" },
    });
    privateKeyPem = privateKey;
    privateKeyPath = path.join(testKeyDir, "test-app.pem");
    fs.writeFileSync(privateKeyPath, privateKeyPem);
  });

  afterEach(() => {
    fs.rmSync(testKeyDir, { recursive: true, force: true });
  });

  it("generateJWT produces a valid 3-part JWT", async () => {
    const { generateJWT } = await import("../auth/github-app");

    const jwt = generateJWT("12345", privateKeyPem);

    // JWT should have 3 base64url parts separated by dots
    const parts = jwt.split(".");
    expect(parts).toHaveLength(3);

    // Decode header
    const header = JSON.parse(Buffer.from(parts[0], "base64url").toString());
    expect(header.alg).toBe("RS256");
    expect(header.typ).toBe("JWT");

    // Decode payload
    const payload = JSON.parse(Buffer.from(parts[1], "base64url").toString());
    expect(payload.iss).toBe("12345");
    expect(payload.exp).toBeGreaterThan(payload.iat);
    // exp should be ~10 minutes after iat
    expect(payload.exp - payload.iat).toBeLessThanOrEqual(11 * 60);
  });

  it("generateJWT uses correct app ID in payload", async () => {
    const { generateJWT } = await import("../auth/github-app");

    const jwt = generateJWT("99999", privateKeyPem);
    const payload = JSON.parse(Buffer.from(jwt.split(".")[1], "base64url").toString());
    expect(payload.iss).toBe("99999");
  });

  it("generateJWT signature is verifiable with RSA-SHA256", async () => {
    const { generateJWT } = await import("../auth/github-app");
    const { createVerify } = await import("crypto");
    const { generateKeyPairSync: genKeys } = await import("crypto");

    // Generate a fresh key pair so we have the public key
    const { privateKey, publicKey } = genKeys("rsa", {
      modulusLength: 2048,
      publicKeyEncoding: { type: "spki", format: "pem" },
      privateKeyEncoding: { type: "pkcs8", format: "pem" },
    });

    const jwt = generateJWT("12345", privateKey);
    const [headerB64, payloadB64, signatureB64] = jwt.split(".");
    const signingInput = `${headerB64}.${payloadB64}`;

    const verify = createVerify("RSA-SHA256");
    verify.update(signingInput);
    const valid = verify.verify(publicKey, signatureB64, "base64url");
    expect(valid).toBe(true);
  });

  it("getGitHubAppToken throws if private key file missing", async () => {
    const { getGitHubAppToken } = await import("../auth/github-app");

    await expect(
      getGitHubAppToken({
        appId: "123",
        privateKeyPath: "/nonexistent/path.pem",
        installationId: "456",
      }),
    ).rejects.toThrow("not found");
  });

  it("testGitHubAppConfig returns invalid if key file missing", async () => {
    const { testGitHubAppConfig } = await import("../auth/github-app");

    const result = await testGitHubAppConfig({
      appId: "123",
      privateKeyPath: "/nonexistent/path.pem",
      installationId: "456",
    });

    expect(result.valid).toBe(false);
    expect(result.error).toContain("not found");
  });

  it("getInstallationToken handles API error", async () => {
    const { getInstallationToken } = await import("../auth/github-app");

    // Mock fetch to return an error
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      text: () => Promise.resolve("Bad credentials"),
    });

    try {
      await expect(
        getInstallationToken("fake-jwt", "12345"),
      ).rejects.toThrow("token exchange failed");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("getInstallationToken returns token on success", async () => {
    const { getInstallationToken } = await import("../auth/github-app");

    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          token: "ghs_test_token_123",
          expires_at: "2026-01-01T00:00:00Z",
        }),
    });

    try {
      const result = await getInstallationToken("fake-jwt", "12345");
      expect(result.token).toBe("ghs_test_token_123");
      expect(result.expiresAt).toBe("2026-01-01T00:00:00Z");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

// ---------------------------------------------------------------------------
// OIDC — Token encryption/decryption
// ---------------------------------------------------------------------------
describe("OIDC token encryption", () => {
  it("encrypt then decrypt round-trips correctly", async () => {
    const { encryptToken, decryptToken } = await import("../auth/oidc");

    const original = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.test-payload.signature";
    const encrypted = encryptToken(original);

    // Encrypted format: iv:authTag:data
    expect(encrypted.split(":")).toHaveLength(3);
    expect(encrypted).not.toContain(original);

    const decrypted = decryptToken(encrypted);
    expect(decrypted).toBe(original);
  });

  it("different encryptions of same token produce different ciphertexts", async () => {
    const { encryptToken } = await import("../auth/oidc");

    const token = "test-token-value";
    const encrypted1 = encryptToken(token);
    const encrypted2 = encryptToken(token);

    // Random IV means different ciphertext each time
    expect(encrypted1).not.toBe(encrypted2);
  });

  it("decryptToken throws on invalid format", async () => {
    const { decryptToken } = await import("../auth/oidc");

    expect(() => decryptToken("not-valid")).toThrow("Invalid encrypted token format");
    expect(() => decryptToken("only:two")).toThrow("Invalid encrypted token format");
  });

  it("decryptToken throws on tampered data", async () => {
    const { encryptToken, decryptToken } = await import("../auth/oidc");

    const encrypted = encryptToken("secret-token");
    const [iv, authTag, data] = encrypted.split(":");

    // Tamper with the encrypted data
    const tampered = `${iv}:${authTag}:${"ff".repeat(data.length / 2)}`;
    expect(() => decryptToken(tampered)).toThrow();
  });
});

// ---------------------------------------------------------------------------
// OIDC — Discovery and flow
// ---------------------------------------------------------------------------
describe("OIDC flow", () => {
  let secretDir: string;
  let secretPath: string;

  beforeEach(() => {
    secretDir = fs.mkdtempSync(path.join(os.tmpdir(), "oidc-test-"));
    secretPath = path.join(secretDir, "client-secret");
    fs.writeFileSync(secretPath, "test-client-secret-value\n");
  });

  afterEach(() => {
    fs.rmSync(secretDir, { recursive: true, force: true });
  });

  it("testOIDCConfig returns invalid if secret file missing", async () => {
    const { testOIDCConfig } = await import("../auth/oidc");

    const result = await testOIDCConfig({
      provider: "gitlab",
      issuerUrl: "https://gitlab.example.com",
      clientId: "test-client",
      clientSecretPath: "/nonexistent/secret",
      scopes: ["openid"],
      redirectUri: "http://localhost:5173/callback",
    });

    expect(result.valid).toBe(false);
    expect(result.error).toContain("not found");
  });

  it("testOIDCConfig returns invalid on discovery failure", async () => {
    const { testOIDCConfig } = await import("../auth/oidc");

    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      text: () => Promise.resolve("Not Found"),
    });

    try {
      const result = await testOIDCConfig({
        provider: "gitlab",
        issuerUrl: "https://gitlab.example.com",
        clientId: "test-client",
        clientSecretPath: secretPath,
        scopes: ["openid"],
        redirectUri: "http://localhost:5173/callback",
      });

      expect(result.valid).toBe(false);
      expect(result.error).toContain("discovery failed");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("testOIDCConfig returns valid on successful discovery", async () => {
    const { testOIDCConfig } = await import("../auth/oidc");

    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          authorization_endpoint: "https://gitlab.example.com/oauth/authorize",
          token_endpoint: "https://gitlab.example.com/oauth/token",
        }),
    });

    try {
      const result = await testOIDCConfig({
        provider: "gitlab",
        issuerUrl: "https://gitlab.example.com",
        clientId: "test-client",
        clientSecretPath: secretPath,
        scopes: ["openid"],
        redirectUri: "http://localhost:5173/callback",
      });

      expect(result.valid).toBe(true);
      expect(result.endpoints?.authorization).toBe("https://gitlab.example.com/oauth/authorize");
      expect(result.endpoints?.token).toBe("https://gitlab.example.com/oauth/token");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("initiateOIDCFlow returns correct authorization URL", async () => {
    const { initiateOIDCFlow } = await import("../auth/oidc");

    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          authorization_endpoint: "https://gitlab.example.com/oauth/authorize",
          token_endpoint: "https://gitlab.example.com/oauth/token",
        }),
    });

    try {
      const url = await initiateOIDCFlow(
        {
          provider: "gitlab",
          issuerUrl: "https://gitlab.example.com",
          clientId: "my-client-id",
          clientSecretPath: secretPath,
          scopes: ["openid", "profile"],
          redirectUri: "http://localhost:5173/callback",
        },
        "random-state-123",
      );

      expect(url).toContain("https://gitlab.example.com/oauth/authorize");
      expect(url).toContain("client_id=my-client-id");
      expect(url).toContain("response_type=code");
      expect(url).toContain("state=random-state-123");
      // URLSearchParams encodes spaces as '+' not '%20'
      expect(url).toContain("scope=openid+profile");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("handleCallback exchanges code for tokens", async () => {
    const { handleCallback } = await import("../auth/oidc");

    const originalFetch = globalThis.fetch;
    let callCount = 0;
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      callCount++;
      if (url.includes(".well-known")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              authorization_endpoint: "https://gitlab.example.com/oauth/authorize",
              token_endpoint: "https://gitlab.example.com/oauth/token",
            }),
        });
      }
      // Token endpoint
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            access_token: "access-token-123",
            refresh_token: "refresh-token-456",
            expires_in: 7200,
            token_type: "Bearer",
          }),
      });
    });

    try {
      const tokenSet = await handleCallback("auth-code-xyz", {
        provider: "gitlab",
        issuerUrl: "https://gitlab.example.com",
        clientId: "my-client-id",
        clientSecretPath: secretPath,
        scopes: ["openid"],
        redirectUri: "http://localhost:5173/callback",
      });

      expect(tokenSet.accessToken).toBe("access-token-123");
      expect(tokenSet.refreshToken).toBe("refresh-token-456");
      expect(tokenSet.tokenType).toBe("Bearer");
      expect(new Date(tokenSet.expiresAt).getTime()).toBeGreaterThan(Date.now());
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("handleCallback throws on token exchange failure", async () => {
    const { handleCallback } = await import("../auth/oidc");

    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes(".well-known")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              authorization_endpoint: "https://gitlab.example.com/oauth/authorize",
              token_endpoint: "https://gitlab.example.com/oauth/token",
            }),
        });
      }
      return Promise.resolve({
        ok: false,
        status: 400,
        text: () => Promise.resolve("invalid_grant"),
      });
    });

    try {
      await expect(
        handleCallback("bad-code", {
          provider: "gitlab",
          issuerUrl: "https://gitlab.example.com",
          clientId: "my-client-id",
          clientSecretPath: secretPath,
          scopes: ["openid"],
          redirectUri: "http://localhost:5173/callback",
        }),
      ).rejects.toThrow("Token exchange failed");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("refreshAccessToken returns new tokens", async () => {
    const { refreshAccessToken } = await import("../auth/oidc");

    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes(".well-known")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              authorization_endpoint: "https://gitlab.example.com/oauth/authorize",
              token_endpoint: "https://gitlab.example.com/oauth/token",
            }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            access_token: "new-access-token",
            refresh_token: "new-refresh-token",
            expires_in: 3600,
            token_type: "Bearer",
          }),
      });
    });

    try {
      const tokenSet = await refreshAccessToken("old-refresh-token", {
        provider: "gitlab",
        issuerUrl: "https://gitlab.example.com",
        clientId: "my-client-id",
        clientSecretPath: secretPath,
        scopes: ["openid"],
        redirectUri: "http://localhost:5173/callback",
      });

      expect(tokenSet.accessToken).toBe("new-access-token");
      expect(tokenSet.refreshToken).toBe("new-refresh-token");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("refreshAccessToken keeps old refresh token when new one not provided", async () => {
    const { refreshAccessToken } = await import("../auth/oidc");

    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes(".well-known")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              authorization_endpoint: "https://gitlab.example.com/oauth/authorize",
              token_endpoint: "https://gitlab.example.com/oauth/token",
            }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            access_token: "new-access-token",
            // No refresh_token in response
            expires_in: 3600,
          }),
      });
    });

    try {
      const tokenSet = await refreshAccessToken("keep-this-refresh-token", {
        provider: "gitlab",
        issuerUrl: "https://gitlab.example.com",
        clientId: "my-client-id",
        clientSecretPath: secretPath,
        scopes: ["openid"],
        redirectUri: "http://localhost:5173/callback",
      });

      expect(tokenSet.refreshToken).toBe("keep-this-refresh-token");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
