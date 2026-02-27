import type { ProviderClient, RepoContext, BranchProtection, RepoMetadata } from "./types";
import { apiFetch } from "./types";

const BASE = "https://gitlab.com";

function projectId(ctx: RepoContext): string {
  return encodeURIComponent(`${ctx.owner}/${ctx.repo}`);
}

export class GitLabClient implements ProviderClient {
  async checkFiles(ctx: RepoContext, paths: string[]): Promise<Record<string, boolean>> {
    const result: Record<string, boolean> = {};
    for (const p of paths) result[p] = false;

    // GitLab tree API is paginated — fetch up to 3 pages (300 items)
    const treePaths = new Set<string>();
    let page = 1;
    while (page <= 3) {
      const url = `${BASE}/api/v4/projects/${projectId(ctx)}/repository/tree?ref=${encodeURIComponent(ctx.branch)}&recursive=true&per_page=100&page=${page}`;
      const res = await apiFetch(url, ctx.accessToken);
      if (!res.ok) break;
      const items = (await res.json()) as { path: string; type: string }[];
      if (items.length === 0) break;
      for (const item of items) treePaths.add(item.path);
      page++;
    }

    const treeArr = Array.from(treePaths);
    for (const p of paths) {
      if (treePaths.has(p)) {
        result[p] = true;
        continue;
      }
      // Directory match
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

    const url = `${BASE}/api/v4/projects/${projectId(ctx)}/protected_branches/${encodeURIComponent(ctx.branch)}`;
    const res = await apiFetch(url, ctx.accessToken);
    if (!res.ok) return none;

    const data = await res.json() as {
      merge_access_levels?: { access_level: number }[];
      push_access_levels?: { access_level: number }[];
      code_owner_approval_required?: boolean;
    };

    // GitLab: if merge access level > 0, it effectively requires review
    const requiresReview = (data.merge_access_levels ?? []).some((l) => l.access_level >= 30);

    return {
      available: true,
      requiresPrReviews: requiresReview || data.code_owner_approval_required === true,
      requiresStatusChecks: null, // GitLab uses pipeline-based protection — not directly queryable here
      requiresSignedCommits: null, // GitLab doesn't expose this per-branch via this API
    };
  }

  async getMetadata(ctx: RepoContext): Promise<RepoMetadata> {
    const url = `${BASE}/api/v4/projects/${projectId(ctx)}`;
    const res = await apiFetch(url, ctx.accessToken);
    if (!res.ok) return { languages: [], topics: [], defaultBranch: ctx.branch, hasIssues: true };

    const data = await res.json() as {
      tag_list?: string[];
      topics?: string[];
      default_branch?: string;
      issues_enabled?: boolean;
    };

    // Fetch languages
    const languages: string[] = [];
    try {
      const langRes = await apiFetch(`${BASE}/api/v4/projects/${projectId(ctx)}/languages`, ctx.accessToken);
      if (langRes.ok) {
        const langData = await langRes.json() as Record<string, number>;
        languages.push(...Object.keys(langData));
      }
    } catch {
      // skip
    }

    return {
      languages,
      topics: data.topics ?? data.tag_list ?? [],
      defaultBranch: data.default_branch ?? ctx.branch,
      hasIssues: data.issues_enabled ?? true,
    };
  }
}
