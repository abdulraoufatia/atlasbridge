import type { ProviderClient, RepoContext, BranchProtection, RepoMetadata } from "./types";
import { apiFetch } from "./types";

const BASE = "https://dev.azure.com";

/** Azure DevOps uses Basic auth with PAT, not Bearer. */
function azureFetch(url: string, token?: string | null): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (token) headers["Authorization"] = `Basic ${Buffer.from(`:${token}`).toString("base64")}`;
  return fetch(url, { headers, signal: AbortSignal.timeout(10_000) });
}

/**
 * Azure DevOps owner format: "org/project"
 * Falls back to treating owner as both org and project if no slash.
 */
function parseOwner(owner: string): { org: string; project: string } {
  const slash = owner.indexOf("/");
  if (slash > 0) return { org: owner.slice(0, slash), project: owner.slice(slash + 1) };
  return { org: owner, project: owner };
}

export class AzureDevOpsClient implements ProviderClient {
  async checkFiles(ctx: RepoContext, paths: string[]): Promise<Record<string, boolean>> {
    const result: Record<string, boolean> = {};
    for (const p of paths) result[p] = false;

    const { org, project } = parseOwner(ctx.owner);
    const url = `${BASE}/${encodeURIComponent(org)}/${encodeURIComponent(project)}/_apis/git/repositories/${encodeURIComponent(ctx.repo)}/items?recursionLevel=full&versionDescriptor.version=${encodeURIComponent(ctx.branch)}&api-version=7.0`;
    const res = await azureFetch(url, ctx.accessToken);
    if (!res.ok) return result;

    const data = await res.json() as { value?: { path: string; isFolder: boolean }[] };
    const treePaths = new Set((data.value ?? []).map((item) => item.path.replace(/^\//, "")));

    const treeArr = Array.from(treePaths);
    for (const p of paths) {
      if (treePaths.has(p)) {
        result[p] = true;
        continue;
      }
      if (!p.includes(".")) {
        const prefix = p.endsWith("/") ? p : p + "/";
        if (treeArr.some((tp) => tp.startsWith(prefix))) {
          result[p] = true;
        }
      }
    }

    return result;
  }

  async checkBranchProtection(ctx: RepoContext): Promise<BranchProtection> {
    const none: BranchProtection = { available: false, requiresPrReviews: null, requiresStatusChecks: null, requiresSignedCommits: null };

    const { org, project } = parseOwner(ctx.owner);

    // First get repository ID
    const repoUrl = `${BASE}/${encodeURIComponent(org)}/${encodeURIComponent(project)}/_apis/git/repositories/${encodeURIComponent(ctx.repo)}?api-version=7.0`;
    const repoRes = await azureFetch(repoUrl, ctx.accessToken);
    if (!repoRes.ok) return none;
    const repoData = await repoRes.json() as { id?: string };
    if (!repoData.id) return none;

    // Fetch branch policies
    const policyUrl = `${BASE}/${encodeURIComponent(org)}/${encodeURIComponent(project)}/_apis/policy/configurations?api-version=7.0`;
    const policyRes = await azureFetch(policyUrl, ctx.accessToken);
    if (!policyRes.ok) return none;

    const policyData = await policyRes.json() as {
      value?: {
        isEnabled: boolean;
        type?: { displayName?: string };
        settings?: { scope?: { repositoryId?: string; refName?: string }[] };
      }[];
    };

    const branchRef = `refs/heads/${ctx.branch}`;
    const branchPolicies = (policyData.value ?? []).filter((p) =>
      p.isEnabled && p.settings?.scope?.some((s) => s.repositoryId === repoData.id && s.refName === branchRef),
    );

    const hasReviewers = branchPolicies.some((p) => p.type?.displayName?.includes("Minimum number of reviewers"));
    const hasStatusChecks = branchPolicies.some((p) => p.type?.displayName?.includes("Build") || p.type?.displayName?.includes("Status"));

    return {
      available: true,
      requiresPrReviews: hasReviewers,
      requiresStatusChecks: hasStatusChecks,
      requiresSignedCommits: null, // Azure DevOps doesn't enforce signed commits
    };
  }

  async getMetadata(ctx: RepoContext): Promise<RepoMetadata> {
    const { org, project } = parseOwner(ctx.owner);
    const url = `${BASE}/${encodeURIComponent(org)}/${encodeURIComponent(project)}/_apis/git/repositories/${encodeURIComponent(ctx.repo)}?api-version=7.0`;
    const res = await azureFetch(url, ctx.accessToken);
    if (!res.ok) return { languages: [], topics: [], defaultBranch: ctx.branch, hasIssues: true };

    const data = await res.json() as {
      defaultBranch?: string;
    };

    return {
      languages: [],
      topics: [],
      defaultBranch: data.defaultBranch?.replace("refs/heads/", "") ?? ctx.branch,
      hasIssues: true,
    };
  }
}
