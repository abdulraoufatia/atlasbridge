import type { ProviderClient, RepoContext, BranchProtection, RepoMetadata } from "./types";
import { apiFetch } from "./types";

const BASE = "https://api.bitbucket.org";

export class BitbucketClient implements ProviderClient {
  async checkFiles(ctx: RepoContext, paths: string[]): Promise<Record<string, boolean>> {
    const result: Record<string, boolean> = {};
    for (const p of paths) result[p] = false;

    // Bitbucket src endpoint lists directory contents — fetch root recursively
    const treePaths = new Set<string>();
    let url: string | null = `${BASE}/2.0/repositories/${ctx.owner}/${ctx.repo}/src/${encodeURIComponent(ctx.branch)}/?pagelen=100`;

    // Follow pagination up to 5 pages
    let pages = 0;
    while (url && pages < 5) {
      const res = await apiFetch(url, ctx.accessToken);
      if (!res.ok) break;
      const data = await res.json() as { values?: { path: string; type: string }[]; next?: string };
      for (const item of data.values ?? []) treePaths.add(item.path);
      url = data.next ?? null;
      pages++;
    }

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

    const url = `${BASE}/2.0/repositories/${ctx.owner}/${ctx.repo}/branch-restrictions?kind=require_approvals_to_merge&pattern=${encodeURIComponent(ctx.branch)}`;
    const res = await apiFetch(url, ctx.accessToken);
    if (!res.ok) return none;

    const data = await res.json() as { values?: { kind: string; value?: number }[] };
    const restrictions = data.values ?? [];

    const hasApproval = restrictions.some((r) => r.kind === "require_approvals_to_merge" && (r.value ?? 0) > 0);

    return {
      available: true,
      requiresPrReviews: hasApproval,
      requiresStatusChecks: null, // Bitbucket uses pipeline-based checks
      requiresSignedCommits: null, // Bitbucket doesn't support signed commit enforcement
    };
  }

  async getMetadata(ctx: RepoContext): Promise<RepoMetadata> {
    const url = `${BASE}/2.0/repositories/${ctx.owner}/${ctx.repo}`;
    const res = await apiFetch(url, ctx.accessToken);
    if (!res.ok) return { languages: [], topics: [], defaultBranch: ctx.branch, hasIssues: true };

    const data = await res.json() as {
      language?: string;
      mainbranch?: { name?: string };
      has_issues?: boolean;
    };

    return {
      languages: data.language ? [data.language] : [],
      topics: [],
      defaultBranch: data.mainbranch?.name ?? ctx.branch,
      hasIssues: data.has_issues ?? true,
    };
  }
}
