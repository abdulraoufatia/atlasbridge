import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import type {
  RepoConnection,
  QualityScanResult,
  QualityCategoryScore,
  QualitySuggestion,
} from "@shared/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  GitBranch,
  Plug,
  Scan,
  ShieldCheck,
  Trash2,
  ArrowLeft,
  CheckCircle2,
  XCircle,
  Clock,
  Plus,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { SiGithub, SiGitlab, SiBitbucket } from "react-icons/si";
import { VscAzureDevops } from "react-icons/vsc";

const providers = [
  { value: "github", label: "GitHub", icon: SiGithub },
  { value: "gitlab", label: "GitLab", icon: SiGitlab },
  { value: "bitbucket", label: "Bitbucket", icon: SiBitbucket },
  { value: "azure", label: "Azure DevOps", icon: VscAzureDevops },
] as const;

const qualityLevels = [
  { value: "basic", label: "Basic" },
  { value: "standard", label: "Standard" },
  { value: "advanced", label: "Advanced" },
];

function getProviderIcon(provider: string) {
  switch (provider) {
    case "github":
      return <SiGithub className="w-5 h-5" />;
    case "gitlab":
      return <SiGitlab className="w-5 h-5" />;
    case "bitbucket":
      return <SiBitbucket className="w-5 h-5" />;
    case "azure":
      return <VscAzureDevops className="w-5 h-5" />;
    default:
      return <Plug className="w-5 h-5" />;
  }
}

function formatDate(date: string | Date | null | undefined): string {
  if (!date) return "Never";
  const d = new Date(date);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function impactBadgeVariant(impact: string) {
  switch (impact) {
    case "critical":
      return "bg-red-500/10 text-red-700 dark:text-red-300";
    case "recommended":
      return "bg-amber-500/10 text-amber-700 dark:text-amber-300";
    case "nice-to-have":
      return "bg-blue-500/10 text-blue-700 dark:text-blue-300";
    default:
      return "";
  }
}

function scoreColor(score: number) {
  if (score >= 80) return "text-emerald-600 dark:text-emerald-400";
  if (score >= 60) return "text-amber-600 dark:text-amber-400";
  return "text-red-600 dark:text-red-400";
}

function ConnectRepoDialog({ onSuccess }: { onSuccess: () => void }) {
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [provider, setProvider] = useState("github");
  const [owner, setOwner] = useState("");
  const [repo, setRepo] = useState("");
  const [branch, setBranch] = useState("main");
  const [accessToken, setAccessToken] = useState("");
  const [qualityLevel, setQualityLevel] = useState("standard");

  const connectMutation = useMutation({
    mutationFn: async () => {
      const url =
        provider === "github"
          ? `https://github.com/${owner}/${repo}`
          : provider === "gitlab"
            ? `https://gitlab.com/${owner}/${repo}`
            : provider === "bitbucket"
              ? `https://bitbucket.org/${owner}/${repo}`
              : `https://dev.azure.com/${owner}/${repo}`;
      await apiRequest("POST", "/api/repo-connections", {
        provider,
        owner,
        repo,
        branch,
        url,
        accessToken: accessToken || undefined,
        connectedBy: "admin",
        qualityLevel,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/repo-connections"] });
      toast({ title: "Repository connected", description: `${owner}/${repo} has been connected.` });
      setOpen(false);
      setOwner("");
      setRepo("");
      setBranch("main");
      setAccessToken("");
      onSuccess();
    },
    onError: (err: Error) => {
      toast({ title: "Connection failed", description: err.message, variant: "destructive" });
    },
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button data-testid="button-connect-repo">
          <Plus className="w-4 h-4 mr-1.5" />
          Connect Repository
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Connect Repository</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label>Provider</Label>
            <Select value={provider} onValueChange={setProvider}>
              <SelectTrigger data-testid="select-provider">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {providers.map((p) => (
                  <SelectItem key={p.value} value={p.value} data-testid={`option-provider-${p.value}`}>
                    <span className="flex items-center gap-2">
                      <p.icon className="w-4 h-4" />
                      {p.label}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label>Owner / Organization</Label>
              <Input
                value={owner}
                onChange={(e) => setOwner(e.target.value)}
                placeholder="owner"
                data-testid="input-owner"
              />
            </div>
            <div className="space-y-2">
              <Label>Repository</Label>
              <Input
                value={repo}
                onChange={(e) => setRepo(e.target.value)}
                placeholder="repo-name"
                data-testid="input-repo"
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label>Branch</Label>
            <Input
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
              placeholder="main"
              data-testid="input-branch"
            />
          </div>
          <div className="space-y-2">
            <Label>Access Token (optional)</Label>
            <Input
              type="password"
              value={accessToken}
              onChange={(e) => setAccessToken(e.target.value)}
              placeholder="ghp_..."
              data-testid="input-access-token"
            />
          </div>
          <div className="space-y-2">
            <Label>Quality Level</Label>
            <Select value={qualityLevel} onValueChange={setQualityLevel}>
              <SelectTrigger data-testid="select-quality-level">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {qualityLevels.map((l) => (
                  <SelectItem key={l.value} value={l.value} data-testid={`option-quality-${l.value}`}>
                    {l.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline" data-testid="button-cancel-connect">
              Cancel
            </Button>
          </DialogClose>
          <Button
            onClick={() => connectMutation.mutate()}
            disabled={!owner || !repo || connectMutation.isPending}
            data-testid="button-submit-connect"
          >
            {connectMutation.isPending ? "Connecting..." : "Connect"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SuggestionsPanel({ suggestions }: { suggestions: QualitySuggestion[] }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <div className="space-y-3">
      <h3 className="text-base font-semibold">Suggestions</h3>
      <div className="grid grid-cols-1 gap-3">
        {suggestions.map((sug: QualitySuggestion) => {
          const isExpanded = expandedId === sug.id;
          return (
            <Card
              key={sug.id}
              data-testid={`suggestion-${sug.id}`}
              className={sug.details ? "cursor-pointer" : ""}
              onClick={() => {
                if (sug.details) setExpandedId(isExpanded ? null : sug.id);
              }}
            >
              <CardContent className="p-4 space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    {sug.details && (
                      isExpanded
                        ? <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0" />
                        : <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />
                    )}
                    {sug.status === "pass" ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    ) : (
                      <XCircle className="w-4 h-4 text-red-500 shrink-0" />
                    )}
                    <span className="text-sm font-medium">{sug.title}</span>
                    <span className="text-xs text-muted-foreground italic">{sug.category}</span>
                  </div>
                  <Badge variant="secondary" className={`text-xs shrink-0 ${impactBadgeVariant(sug.impact)}`}>
                    {sug.impact}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground">{sug.description}</p>
                {isExpanded && sug.details && (
                  <div className="mt-3 pt-3 border-t">
                    <p className="text-xs font-medium mb-2">How to fix</p>
                    <pre className="text-xs text-muted-foreground whitespace-pre-wrap font-sans leading-relaxed">{sug.details}</pre>
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function RepoDetailView({
  repo,
  onBack,
}: {
  repo: RepoConnection;
  onBack: () => void;
}) {
  const { toast } = useToast();
  const [scanLevel, setScanLevel] = useState(repo.qualityLevel || "standard");
  const [scanResult, setScanResult] = useState<QualityScanResult | null>(null);

  const { data: scanHistory, isLoading: historyLoading } = useQuery<QualityScanResult[]>({
    queryKey: ["/api/repo-connections", repo.id, "scans"],
  });

  const scanMutation = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("POST", `/api/repo-connections/${repo.id}/scan`, {
        qualityLevel: scanLevel,
      });
      return (await res.json()) as QualityScanResult;
    },
    onSuccess: (data) => {
      setScanResult(data);
      queryClient.invalidateQueries({ queryKey: ["/api/repo-connections"] });
      queryClient.invalidateQueries({ queryKey: ["/api/repo-connections", repo.id, "scans"] });
      toast({ title: "Scan complete", description: `Score: ${data.overallScore}/100` });
    },
    onError: (err: Error) => {
      toast({ title: "Scan failed", description: err.message, variant: "destructive" });
    },
  });

  const disconnectMutation = useMutation({
    mutationFn: async () => {
      await apiRequest("DELETE", `/api/repo-connections/${repo.id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/repo-connections"] });
      toast({ title: "Repository disconnected" });
      onBack();
    },
    onError: (err: Error) => {
      toast({ title: "Failed to disconnect", description: err.message, variant: "destructive" });
    },
  });

  const displayResult = scanResult || (scanHistory && scanHistory.length > 0 ? scanHistory[0] : null);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 flex-wrap">
        <Button variant="ghost" size="icon" onClick={onBack} data-testid="button-back">
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <div className="flex items-center gap-2">
          {getProviderIcon(repo.provider)}
          <h2 className="text-lg font-semibold" data-testid={`text-repo-name-${repo.id}`}>
            {repo.owner}/{repo.repo}
          </h2>
        </div>
        <Badge variant="outline" className="ml-auto">
          <GitBranch className="w-3 h-3 mr-1" />
          {repo.branch}
        </Badge>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardContent className="p-4 space-y-1">
            <p className="text-xs text-muted-foreground">Status</p>
            <Badge
              variant="outline"
              className={
                repo.status === "connected"
                  ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                  : "bg-red-500/10 text-red-700 dark:text-red-300"
              }
              data-testid={`text-status-${repo.id}`}
            >
              {repo.status}
            </Badge>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 space-y-1">
            <p className="text-xs text-muted-foreground">Quality Score</p>
            <p className={`text-2xl font-semibold ${scoreColor(repo.qualityScore ?? 0)}`} data-testid={`text-score-${repo.id}`}>
              {repo.qualityScore != null ? `${repo.qualityScore}/100` : "N/A"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 space-y-1">
            <p className="text-xs text-muted-foreground">Last Synced</p>
            <p className="text-sm flex items-center gap-1.5" data-testid={`text-synced-${repo.id}`}>
              <Clock className="w-3.5 h-3.5 text-muted-foreground" />
              {formatDate(repo.lastSynced)}
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 pb-2">
          <CardTitle className="text-base">Run Quality Scan</CardTitle>
        </CardHeader>
        <CardContent className="flex items-end gap-3 flex-wrap">
          <div className="space-y-2">
            <Label className="text-xs">Quality Level</Label>
            <Select value={scanLevel} onValueChange={setScanLevel}>
              <SelectTrigger className="w-[160px]" data-testid="select-scan-level">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {qualityLevels.map((l) => (
                  <SelectItem key={l.value} value={l.value}>
                    {l.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button
            onClick={() => scanMutation.mutate()}
            disabled={scanMutation.isPending}
            data-testid="button-run-scan"
          >
            <Scan className="w-4 h-4 mr-1.5" />
            {scanMutation.isPending ? "Scanning..." : "Run Scan"}
          </Button>
          <div className="ml-auto">
            <Button
              variant="outline"
              className="text-red-600 dark:text-red-400"
              onClick={() => disconnectMutation.mutate()}
              disabled={disconnectMutation.isPending}
              data-testid="button-disconnect"
            >
              <Trash2 className="w-4 h-4 mr-1.5" />
              Disconnect
            </Button>
          </div>
        </CardContent>
      </Card>

      {displayResult && (
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <h3 className="text-base font-semibold flex items-center gap-2">
              <ShieldCheck className="w-4 h-4" />
              Scan Results
            </h3>
            <p className="text-xs text-muted-foreground">
              Scanned: {formatDate(displayResult.scannedAt)} &middot; Level: {displayResult.qualityLevel}
            </p>
          </div>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
                <span className="text-sm font-medium">Overall Score</span>
                <span className={`text-lg font-bold ${scoreColor(displayResult.overallScore)}`} data-testid="text-overall-score">
                  {displayResult.overallScore}/100
                </span>
              </div>
              <Progress value={displayResult.overallScore} className="h-2" />
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {displayResult.categories.map((cat: QualityCategoryScore) => (
              <Card key={cat.name}>
                <CardHeader className="pb-2 space-y-0">
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <CardTitle className="text-sm">{cat.name}</CardTitle>
                    <span className={`text-sm font-semibold ${scoreColor((cat.score / cat.maxScore) * 100)}`} data-testid={`text-category-score-${cat.name}`}>
                      {cat.score}/{cat.maxScore}
                    </span>
                  </div>
                </CardHeader>
                <CardContent className="space-y-2">
                  <Progress value={(cat.score / cat.maxScore) * 100} className="h-1.5" />
                  <div className="space-y-1">
                    {cat.checks.map((check) => (
                      <div
                        key={check.name}
                        className="flex items-start gap-2 text-xs"
                        data-testid={`check-${check.name}`}
                      >
                        {check.passed ? (
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 mt-0.5 shrink-0" />
                        ) : (
                          <XCircle className="w-3.5 h-3.5 text-red-500 mt-0.5 shrink-0" />
                        )}
                        <div>
                          <span className="font-medium">{check.name}</span>
                          <span className="text-muted-foreground ml-1">{check.detail}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {displayResult.suggestions.length > 0 && (
            <SuggestionsPanel suggestions={displayResult.suggestions} />
          )}
        </div>
      )}

      {historyLoading && (
        <div className="space-y-3">
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-24 w-full" />
        </div>
      )}
    </div>
  );
}

export default function RepositoriesPage() {
  const [selectedRepoId, setSelectedRepoId] = useState<number | null>(null);

  const { data: repos, isLoading } = useQuery<RepoConnection[]>({
    queryKey: ["/api/repo-connections"],
  });

  const selectedRepo = repos?.find((r) => r.id === selectedRepoId);

  if (selectedRepo) {
    return (
      <RepoDetailView
        repo={selectedRepo}
        onBack={() => setSelectedRepoId(null)}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Repositories</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Connect repositories and generate governance evidence
          </p>
        </div>
        <ConnectRepoDialog onSuccess={() => {}} />
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-4">
                <Skeleton className="h-20 w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {!isLoading && repos && repos.length === 0 && (
        <Card>
          <CardContent className="p-8 text-center space-y-3">
            <Plug className="w-10 h-10 text-muted-foreground mx-auto" />
            <p className="text-sm text-muted-foreground" data-testid="text-empty-repos">
              No repositories connected yet. Connect your first repository to start generating governance evidence.
            </p>
          </CardContent>
        </Card>
      )}

      {!isLoading && repos && repos.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {repos.map((repo) => (
            <Card
              key={repo.id}
              className="cursor-pointer hover-elevate"
              onClick={() => setSelectedRepoId(repo.id)}
              data-testid={`card-repo-${repo.id}`}
            >
              <CardContent className="p-4 space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    {getProviderIcon(repo.provider)}
                    <span className="text-sm font-medium truncate">
                      {repo.owner}/{repo.repo}
                    </span>
                  </div>
                  <Badge
                    variant="outline"
                    className={
                      repo.status === "connected"
                        ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 shrink-0"
                        : "bg-red-500/10 text-red-700 dark:text-red-300 shrink-0"
                    }
                  >
                    {repo.status}
                  </Badge>
                </div>

                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <GitBranch className="w-3 h-3" />
                  {repo.branch}
                  <span className="ml-auto flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {formatDate(repo.lastSynced)}
                  </span>
                </div>

                <div className="space-y-1">
                  <div className="flex items-center justify-between gap-2 text-xs">
                    <span className="text-muted-foreground">Quality</span>
                    <span className={`font-medium ${scoreColor(repo.qualityScore ?? 0)}`} data-testid={`text-card-score-${repo.id}`}>
                      {repo.qualityScore != null ? `${repo.qualityScore}%` : "N/A"}
                    </span>
                  </div>
                  {repo.qualityScore != null && (
                    <Progress value={repo.qualityScore} className="h-1.5" />
                  )}
                </div>

                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Badge variant="secondary" className="text-xs">
                    {repo.qualityLevel}
                  </Badge>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
