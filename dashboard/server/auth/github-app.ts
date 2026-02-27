/**
 * GitHub App authentication — JWT generation and installation token exchange.
 * Uses native crypto (no jsonwebtoken dependency).
 */

import fs from "fs";
import { createSign } from "crypto";

const GITHUB_API = "https://api.github.com";

export interface GitHubAppConfig {
  appId: string;
  privateKeyPath: string;   // path to .pem file
  installationId: string;
}

/**
 * Generate a JWT for GitHub App authentication.
 * JWTs have a max lifetime of 10 minutes.
 */
export function generateJWT(appId: string, privateKeyPem: string): string {
  const now = Math.floor(Date.now() / 1000);

  const header = {
    alg: "RS256",
    typ: "JWT",
  };

  const payload = {
    iat: now - 60,        // issued at (60s clock skew)
    exp: now + 10 * 60,   // 10 minute expiry
    iss: appId,
  };

  const encodedHeader = base64url(JSON.stringify(header));
  const encodedPayload = base64url(JSON.stringify(payload));
  const signingInput = `${encodedHeader}.${encodedPayload}`;

  const sign = createSign("RSA-SHA256");
  sign.update(signingInput);
  const signature = sign.sign(privateKeyPem, "base64url");

  return `${signingInput}.${signature}`;
}

function base64url(input: string): string {
  return Buffer.from(input)
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

/**
 * Exchange a JWT for an installation access token.
 * Installation tokens last 1 hour.
 */
export async function getInstallationToken(
  jwt: string,
  installationId: string,
): Promise<{ token: string; expiresAt: string }> {
  const res = await fetch(`${GITHUB_API}/app/installations/${installationId}/access_tokens`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${jwt}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    signal: AbortSignal.timeout(10_000),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`GitHub App token exchange failed (${res.status}): ${body}`);
  }

  const data = (await res.json()) as { token: string; expires_at: string };
  return { token: data.token, expiresAt: data.expires_at };
}

/**
 * Get an access token for a GitHub App installation.
 * Reads the private key from disk, generates JWT, exchanges for installation token.
 */
export async function getGitHubAppToken(config: GitHubAppConfig): Promise<string> {
  if (!fs.existsSync(config.privateKeyPath)) {
    throw new Error(`GitHub App private key not found at: ${config.privateKeyPath}`);
  }

  const privateKey = fs.readFileSync(config.privateKeyPath, "utf-8");
  const jwt = generateJWT(config.appId, privateKey);
  const { token } = await getInstallationToken(jwt, config.installationId);
  return token;
}

/**
 * Validate a GitHub App configuration by attempting token exchange.
 */
export async function testGitHubAppConfig(config: GitHubAppConfig): Promise<{
  valid: boolean;
  error?: string;
  installationInfo?: { account: string; appSlug: string };
}> {
  try {
    if (!fs.existsSync(config.privateKeyPath)) {
      return { valid: false, error: `Private key file not found: ${config.privateKeyPath}` };
    }

    const privateKey = fs.readFileSync(config.privateKeyPath, "utf-8");
    const jwt = generateJWT(config.appId, privateKey);

    // Verify the JWT works by listing installations
    const res = await fetch(`${GITHUB_API}/app/installations/${config.installationId}`, {
      headers: {
        Authorization: `Bearer ${jwt}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      signal: AbortSignal.timeout(10_000),
    });

    if (!res.ok) {
      const body = await res.text();
      return { valid: false, error: `API returned ${res.status}: ${body}` };
    }

    const data = (await res.json()) as { account?: { login?: string }; app_slug?: string };
    return {
      valid: true,
      installationInfo: {
        account: data.account?.login || "unknown",
        appSlug: data.app_slug || "unknown",
      },
    };
  } catch (err: any) {
    return { valid: false, error: err.message || "Unknown error" };
  }
}
