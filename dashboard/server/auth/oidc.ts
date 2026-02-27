/**
 * Generic OIDC authentication — supports GitLab and Azure AD.
 * Implements authorization code flow with token refresh.
 */

import fs from "fs";
import { createCipheriv, createDecipheriv, randomBytes, scryptSync } from "crypto";
import os from "os";

export interface OIDCConfig {
  provider: "gitlab" | "azure";
  issuerUrl: string;
  clientId: string;
  clientSecretPath: string;  // file path, not inline
  scopes: string[];
  redirectUri: string;
}

export interface TokenSet {
  accessToken: string;
  refreshToken: string | null;
  expiresAt: string;
  tokenType: string;
}

// ---------------------------------------------------------------------------
// Token encryption — encrypts tokens at rest using machine-derived key
// ---------------------------------------------------------------------------

function deriveKey(): Buffer {
  // Derive a key from machine-specific data
  const machineId = `${os.hostname()}-${os.userInfo().username}-atlasbridge`;
  return scryptSync(machineId, "atlasbridge-oidc-salt", 32);
}

export function encryptToken(token: string): string {
  const key = deriveKey();
  const iv = randomBytes(16);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  let encrypted = cipher.update(token, "utf-8", "hex");
  encrypted += cipher.final("hex");
  const authTag = cipher.getAuthTag().toString("hex");
  return `${iv.toString("hex")}:${authTag}:${encrypted}`;
}

export function decryptToken(encrypted: string): string {
  const key = deriveKey();
  const [ivHex, authTagHex, data] = encrypted.split(":");
  if (!ivHex || !authTagHex || !data) throw new Error("Invalid encrypted token format");
  const iv = Buffer.from(ivHex, "hex");
  const authTag = Buffer.from(authTagHex, "hex");
  const decipher = createDecipheriv("aes-256-gcm", key, iv);
  decipher.setAuthTag(authTag);
  let decrypted = decipher.update(data, "hex", "utf-8");
  decrypted += decipher.final("utf-8");
  return decrypted;
}

// ---------------------------------------------------------------------------
// OIDC Discovery
// ---------------------------------------------------------------------------

interface OIDCDiscovery {
  authorization_endpoint: string;
  token_endpoint: string;
  userinfo_endpoint?: string;
}

async function discover(issuerUrl: string): Promise<OIDCDiscovery> {
  const wellKnown = `${issuerUrl.replace(/\/+$/, "")}/.well-known/openid-configuration`;
  const res = await fetch(wellKnown, { signal: AbortSignal.timeout(10_000) });
  if (!res.ok) throw new Error(`OIDC discovery failed (${res.status}): ${await res.text()}`);
  return (await res.json()) as OIDCDiscovery;
}

// ---------------------------------------------------------------------------
// Authorization flow
// ---------------------------------------------------------------------------

/**
 * Generate the authorization URL to redirect the user to.
 */
export async function initiateOIDCFlow(config: OIDCConfig, state: string): Promise<string> {
  const disco = await discover(config.issuerUrl);

  const params = new URLSearchParams({
    client_id: config.clientId,
    redirect_uri: config.redirectUri,
    response_type: "code",
    scope: config.scopes.join(" "),
    state,
  });

  return `${disco.authorization_endpoint}?${params.toString()}`;
}

/**
 * Exchange an authorization code for tokens.
 */
export async function handleCallback(
  code: string,
  config: OIDCConfig,
): Promise<TokenSet> {
  const disco = await discover(config.issuerUrl);
  const clientSecret = readClientSecret(config.clientSecretPath);

  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    redirect_uri: config.redirectUri,
    client_id: config.clientId,
    client_secret: clientSecret,
  });

  const res = await fetch(disco.token_endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
    signal: AbortSignal.timeout(10_000),
  });

  if (!res.ok) {
    const errBody = await res.text();
    throw new Error(`Token exchange failed (${res.status}): ${errBody}`);
  }

  const data = (await res.json()) as {
    access_token: string;
    refresh_token?: string;
    expires_in?: number;
    token_type?: string;
  };

  return {
    accessToken: data.access_token,
    refreshToken: data.refresh_token || null,
    expiresAt: new Date(Date.now() + (data.expires_in || 3600) * 1000).toISOString(),
    tokenType: data.token_type || "Bearer",
  };
}

/**
 * Refresh an access token using a refresh token.
 */
export async function refreshAccessToken(
  currentRefreshToken: string,
  config: OIDCConfig,
): Promise<TokenSet> {
  const disco = await discover(config.issuerUrl);
  const clientSecret = readClientSecret(config.clientSecretPath);

  const body = new URLSearchParams({
    grant_type: "refresh_token",
    refresh_token: currentRefreshToken,
    client_id: config.clientId,
    client_secret: clientSecret,
  });

  const res = await fetch(disco.token_endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
    signal: AbortSignal.timeout(10_000),
  });

  if (!res.ok) {
    const errBody = await res.text();
    throw new Error(`Token refresh failed (${res.status}): ${errBody}`);
  }

  const data = (await res.json()) as {
    access_token: string;
    refresh_token?: string;
    expires_in?: number;
    token_type?: string;
  };

  return {
    accessToken: data.access_token,
    refreshToken: data.refresh_token || currentRefreshToken,
    expiresAt: new Date(Date.now() + (data.expires_in || 3600) * 1000).toISOString(),
    tokenType: data.token_type || "Bearer",
  };
}

/**
 * Test OIDC configuration by performing discovery.
 */
export async function testOIDCConfig(config: OIDCConfig): Promise<{
  valid: boolean;
  error?: string;
  endpoints?: { authorization: string; token: string };
}> {
  try {
    if (!fs.existsSync(config.clientSecretPath)) {
      return { valid: false, error: `Client secret file not found: ${config.clientSecretPath}` };
    }

    const disco = await discover(config.issuerUrl);
    return {
      valid: true,
      endpoints: {
        authorization: disco.authorization_endpoint,
        token: disco.token_endpoint,
      },
    };
  } catch (err: any) {
    return { valid: false, error: err.message || "Unknown error" };
  }
}

function readClientSecret(secretPath: string): string {
  if (!fs.existsSync(secretPath)) {
    throw new Error(`Client secret file not found: ${secretPath}`);
  }
  return fs.readFileSync(secretPath, "utf-8").trim();
}
