export interface RepoContext {
  provider: string;
  owner: string;
  repo: string;
  branch: string;
  accessToken?: string | null;
}

export interface BranchProtection {
  available: boolean;
  requiresPrReviews: boolean | null;
  requiresStatusChecks: boolean | null;
  requiresSignedCommits: boolean | null;
}

export interface RepoMetadata {
  languages: string[];
  topics: string[];
  defaultBranch: string;
  hasIssues: boolean;
}

export interface RepoSnapshot {
  files: Record<string, boolean>;
  branchProtection: BranchProtection;
  metadata: RepoMetadata;
  errors: string[];
}

export interface ProviderClient {
  checkFiles(ctx: RepoContext, paths: string[]): Promise<Record<string, boolean>>;
  checkBranchProtection(ctx: RepoContext): Promise<BranchProtection>;
  getMetadata(ctx: RepoContext): Promise<RepoMetadata>;
}

export async function apiFetch(url: string, token?: string | null): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return fetch(url, { headers, signal: AbortSignal.timeout(10_000) });
}
