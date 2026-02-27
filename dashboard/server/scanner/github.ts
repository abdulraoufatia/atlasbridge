import type { ProviderClient, RepoContext, BranchProtection, RepoMetadata } from "./types";
import { apiFetch } from "./types";

const BASE = "https://api.github.com";

export class GitHubClient implements ProviderClient {
  async checkFiles(ctx: RepoContext, paths: string[]): Promise<Record<string, boolean>> {
    const result: Record<string, boolean> = {};
    for (const p of paths) result[p] = false;

    const url = `${BASE}/repos/${ctx.owner}/${ctx.repo}/git/trees/${ctx.branch}?recursive=1`;
    const res = await apiFetch(url, ctx.accessToken);
    if (!res.ok) return result;

    const data = await res.json() as { tree?: { path: string; type: string }[]; truncated?: boolean };
    const treePaths = new Set((data.tree ?? []).map((e) => e.path));

    const treeArr = Array.from(treePaths);
    for (const p of paths) {
      // Direct match
      if (treePaths.has(p)) {
        result[p] = true;
        continue;
      }
      // Directory match — check if any tree entry starts with the path prefix
      if (p.endsWith("/") || !p.includes(".")) {
        const prefix = p.endsWith("/") ? p : p + "/";
        if (treeArr.some((tp) => tp.startsWith(prefix) || tp === p)) {
          result[p] = true;
        }
      }
    }

    return result;
  }

  async checkBranchProtection(ctx: RepoContext): Promise<BranchProtection> {
    const none: BranchProtection = { available: false, requiresPrReviews: null, requiresStatusChecks: null, requiresSignedCommits: null };

    const url = `${BASE}/repos/${ctx.owner}/${ctx.repo}/branches/${ctx.branch}/protection`;
    const res = await apiFetch(url, ctx.accessToken);
    if (!res.ok) return none;

    const data = await res.json() as {
      required_pull_request_reviews?: unknown;
      required_status_checks?: unknown;
      required_signatures?: { enabled?: boolean };
    };

    return {
      available: true,
      requiresPrReviews: data.required_pull_request_reviews != null,
      requiresStatusChecks: data.required_status_checks != null,
      requiresSignedCommits: data.required_signatures?.enabled ?? null,
    };
  }

  async getMetadata(ctx: RepoContext): Promise<RepoMetadata> {
    const url = `${BASE}/repos/${ctx.owner}/${ctx.repo}`;
    const res = await apiFetch(url, ctx.accessToken);
    if (!res.ok) return { languages: [], topics: [], defaultBranch: ctx.branch, hasIssues: true };

    const data = await res.json() as {
      language?: string;
      topics?: string[];
      default_branch?: string;
      has_issues?: boolean;
    };

    // Fetch languages list
    const languages: string[] = data.language ? [data.language] : [];
    try {
      const langRes = await apiFetch(`${BASE}/repos/${ctx.owner}/${ctx.repo}/languages`, ctx.accessToken);
      if (langRes.ok) {
        const langData = await langRes.json() as Record<string, number>;
        languages.length = 0;
        languages.push(...Object.keys(langData));
      }
    } catch {
      // keep primary language only
    }

    return {
      languages,
      topics: data.topics ?? [],
      defaultBranch: data.default_branch ?? ctx.branch,
      hasIssues: data.has_issues ?? true,
    };
  }
}
