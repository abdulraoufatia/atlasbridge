import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import type {
  RepoConnection,
  QualityScanResult,
  QualityCategoryScore,
  QualitySuggestion,
  LocalScanResult,
  ScanProfile,
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
  Download,
  FolderSearch,
  AlertTriangle,
  Lock,
  FileCode,
  Shield,
  Eye,
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

const scanProfiles = [
  { value: "quick", label: "Quick", description: "Inventory only" },
  { value: "safety", label: "Safety", description: "Inventory + boundaries" },
  { value: "deep", label: "Deep", description: "Full analysis + secrets" },
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

function riskBadge(risk: string) {
  switch (risk) {
    case "high":
      return "bg-red-500/10 text-red-700 dark:text-red-300";
    case "medium":
      return "bg-amber-500/10 text-amber-700 dark:text-amber-300";
    case "low":
      return "bg-blue-500/10 text-blue-700 dark:text-blue-300";
    case "incompatible":
      return "bg-red-500/10 text-red-700 dark:text-red-300";
    case "review":
      return "bg-amber-500/10 text-amber-700 dark:text-amber-300";
    case "compatible":
      return "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
    default:
      return "";
  }
}

// ---------------------------------------------------------------------------
// Connect Dialog
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Suggestions Panel (existing)
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Local Scan Results Panels
// ---------------------------------------------------------------------------

function InventoryPanel({ result }: { result: LocalScanResult }) {
  const inv = result.inventory;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card>
          <CardContent className="p-3">
            <p className="text-xs text-muted-foreground">Files</p>
            <p className="text-lg font-semibold">{inv.totalFiles.toLocaleString()}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-3">
            <p className="text-xs text-muted-foreground">Lines</p>
            <p className="text-lg font-semibold">{inv.totalLines.toLocaleString()}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-3">
            <p className="text-xs text-muted-foreground">Size</p>
            <p className="text-lg font-semibold">{inv.repoSize}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-3">
            <p className="text-xs text-muted-foreground">Type</p>
            <p className="text-lg font-semibold capitalize">{inv.projectType}</p>
          </CardContent>
        </Card>
      </div>

      {inv.languages.length > 0 && (
        <Card>
          <CardHeader className="pb-2 space-y-0">
            <CardTitle className="text-sm flex items-center gap-2">
              <FileCode className="w-4 h-4" /> Languages
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {inv.languages.slice(0, 10).map((lang) => (
              <div key={lang.name} className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-medium">{lang.name}</span>
                  <span className="text-muted-foreground">{lang.percentage}% ({lang.files} files)</span>
                </div>
                <Progress value={lang.percentage} className="h-1.5" />
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {inv.buildSystems.length > 0 && (
          <Card>
            <CardHeader className="pb-2 space-y-0">
              <CardTitle className="text-sm">Build Systems</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-1.5">
                {inv.buildSystems.map((bs) => (
                  <Badge key={bs} variant="secondary" className="text-xs">{bs}</Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {inv.ciPlatforms.length > 0 && (
          <Card>
            <CardHeader className="pb-2 space-y-0">
              <CardTitle className="text-sm">CI Platforms</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-1.5">
                {inv.ciPlatforms.map((ci) => (
                  <Badge key={ci} variant="secondary" className="text-xs">{ci}</Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {inv.frameworks.length > 0 && (
          <Card>
            <CardHeader className="pb-2 space-y-0">
              <CardTitle className="text-sm">Frameworks</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-1.5">
                {inv.frameworks.map((fw) => (
                  <Badge key={fw} variant="secondary" className="text-xs">{fw}</Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

function SafetyPanel({ result }: { result: LocalScanResult }) {
  if (!result.safetyBoundaries) {
    return (
      <Card>
        <CardContent className="p-6 text-center text-sm text-muted-foreground">
          Safety boundaries require Safety or Deep profile scan.
        </CardContent>
      </Card>
    );
  }

  const sb = result.safetyBoundaries;
  return (
    <div className="space-y-4">
      {sb.sensitivePaths.length > 0 && (
        <Card>
          <CardHeader className="pb-2 space-y-0">
            <CardTitle className="text-sm flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" /> Sensitive Paths ({sb.sensitivePaths.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1.5 max-h-64 overflow-y-auto">
              {sb.sensitivePaths.map((sp, i) => (
                <div key={i} className="flex items-start gap-2 text-xs">
                  <Badge variant="secondary" className={`text-[10px] shrink-0 mt-0.5 ${riskBadge(sp.risk)}`}>
                    {sp.risk}
                  </Badge>
                  <code className="font-mono text-xs">{sp.path}</code>
                  <span className="text-muted-foreground ml-auto shrink-0">{sp.reason}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {sb.toolSurfaces.length > 0 && (
        <Card>
          <CardHeader className="pb-2 space-y-0">
            <CardTitle className="text-sm flex items-center gap-2">
              <Eye className="w-4 h-4" /> Tool Surfaces
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {sb.toolSurfaces.map((ts, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <span className="font-medium">{ts.tool}</span>
                  <code className="text-muted-foreground font-mono">{ts.configPath}</code>
                  <span className="text-muted-foreground ml-auto">{ts.risk}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {sb.ciSafetyChecks.length > 0 && (
        <Card>
          <CardHeader className="pb-2 space-y-0">
            <CardTitle className="text-sm flex items-center gap-2">
              <Shield className="w-4 h-4" /> CI Safety Checks
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1.5">
              {sb.ciSafetyChecks.map((check, i) => (
                <div key={i} className="flex items-start gap-2 text-xs">
                  {check.present ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 mt-0.5 shrink-0" />
                  ) : (
                    <XCircle className="w-3.5 h-3.5 text-red-500 mt-0.5 shrink-0" />
                  )}
                  <span className="font-medium">{check.name}</span>
                  <span className="text-muted-foreground">{check.detail}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {sb.policyCoverage === null && (
        <Card>
          <CardContent className="p-4 text-xs text-muted-foreground">
            Policy coverage analysis requires the AtlasBridge CLI to be installed.
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function SecurityPanel({ result }: { result: LocalScanResult }) {
  if (!result.securitySignals) {
    return (
      <Card>
        <CardContent className="p-6 text-center text-sm text-muted-foreground">
          Security signals require Deep profile scan.
        </CardContent>
      </Card>
    );
  }

  const ss = result.securitySignals;
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2 space-y-0">
          <CardTitle className="text-sm flex items-center gap-2">
            <Lock className="w-4 h-4" /> Secret Findings ({ss.totalSecretsFound})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {ss.secretFindings.length === 0 ? (
            <p className="text-xs text-muted-foreground flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
              No secrets detected in source files
            </p>
          ) : (
            <div className="space-y-1.5 max-h-48 overflow-y-auto">
              {ss.secretFindings.slice(0, 30).map((sf, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <AlertTriangle className="w-3 h-3 text-red-500 shrink-0" />
                  <code className="font-mono">{sf.file}:{sf.line}</code>
                  <Badge variant="secondary" className="text-[10px]">{sf.type}</Badge>
                  <span className="text-muted-foreground ml-auto font-mono text-[10px]">{sf.fingerprint}</span>
                </div>
              ))}
              {ss.secretFindings.length > 30 && (
                <p className="text-xs text-muted-foreground">... and {ss.secretFindings.length - 30} more</p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {ss.dependencyRisks.length > 0 && (
        <Card>
          <CardHeader className="pb-2 space-y-0">
            <CardTitle className="text-sm">Dependency Risks ({ss.dependencyRisks.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1.5 max-h-48 overflow-y-auto">
              {ss.dependencyRisks.slice(0, 20).map((dr, i) => (
                <div key={i} className="flex items-start gap-2 text-xs">
                  <AlertTriangle className="w-3 h-3 text-amber-500 mt-0.5 shrink-0" />
                  <span className="font-medium">{dr.name}@{dr.version}</span>
                  <span className="text-muted-foreground">{dr.detail}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {ss.licenseInventory.length > 0 && (
        <Card>
          <CardHeader className="pb-2 space-y-0">
            <CardTitle className="text-sm">License Inventory ({ss.licenseInventory.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1.5 max-h-48 overflow-y-auto">
              {ss.licenseInventory.slice(0, 30).map((le, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <span className="font-medium min-w-0 truncate">{le.name}</span>
                  <Badge variant="secondary" className={`text-[10px] shrink-0 ${riskBadge(le.risk)}`}>
                    {le.license}
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {ss.vulnerabilities && ss.vulnerabilities.length > 0 && (
        <Card>
          <CardHeader className="pb-2 space-y-0">
            <CardTitle className="text-sm flex items-center gap-2">
              <Shield className="w-4 h-4" /> CVE Vulnerabilities ({ss.totalVulnerabilities ?? ss.vulnerabilities.length})
              {(ss.criticalVulnerabilities ?? 0) > 0 && (
                <Badge variant="destructive" className="text-[10px]">{ss.criticalVulnerabilities} critical</Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1.5 max-h-64 overflow-y-auto">
              {ss.vulnerabilities.slice(0, 40).map((v, i) => (
                <div key={i} className="flex items-start gap-2 text-xs">
                  <Badge variant={v.severity === "critical" ? "destructive" : v.severity === "high" ? "destructive" : "secondary"} className="text-[10px] shrink-0">
                    {v.severity}
                  </Badge>
                  <span className="font-mono">{v.cveId}</span>
                  <span className="font-medium">{v.packageName}@{v.packageVersion}</span>
                  <span className="text-muted-foreground truncate">{v.summary}</span>
                  {v.fixVersion && <span className="ml-auto text-emerald-600 text-[10px] shrink-0">fix: {v.fixVersion}</span>}
                </div>
              ))}
              {ss.vulnerabilities.length > 40 && (
                <p className="text-xs text-muted-foreground">... and {ss.vulnerabilities.length - 40} more</p>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab component (simple)
// ---------------------------------------------------------------------------

function TabBar({ tabs, active, onChange }: { tabs: { key: string; label: string; icon?: React.ReactNode }[]; active: string; onChange: (key: string) => void }) {
  return (
    <div className="flex gap-1 border-b">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
            active === tab.key
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
          onClick={() => onChange(tab.key)}
        >
          {tab.icon}
          {tab.label}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Repo Detail View
// ---------------------------------------------------------------------------

function RepoDetailView({
  repo,
  onBack,
}: {
  repo: RepoConnection;
  onBack: () => void;
}) {
  const { toast } = useToast();
  const [scanTab, setScanTab] = useState<"api" | "local" | "cloud">("api");
  const [scanLevel, setScanLevel] = useState(repo.qualityLevel || "standard");
  const [scanResult, setScanResult] = useState<QualityScanResult | null>(null);

  // Local scan state
  const [localProfile, setLocalProfile] = useState<ScanProfile>("quick");
  const [localPath, setLocalPath] = useState("");
  const [localResult, setLocalResult] = useState<LocalScanResult | null>(null);
  const [localResultTab, setLocalResultTab] = useState("snapshot");

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

  const localScanMutation = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("POST", `/api/repo-connections/${repo.id}/local-scan`, {
        profile: localProfile,
        localPath: localPath || undefined,
      });
      return (await res.json()) as LocalScanResult;
    },
    onSuccess: (data) => {
      setLocalResult(data);
      queryClient.invalidateQueries({ queryKey: ["/api/repo-connections"] });
      toast({ title: "Local scan complete", description: `Profile: ${data.profile}, ${data.inventory.totalFiles} files scanned in ${data.duration}ms` });
    },
    onError: (err: Error) => {
      toast({ title: "Local scan failed", description: err.message, variant: "destructive" });
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

  // Cloud scan mutations
  const [containerImage, setContainerImage] = useState("");
  const [containerTag, setContainerTag] = useState("latest");

  const remoteScanMutation = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("POST", `/api/repo-connections/${repo.id}/remote-scan`, {});
      return res.json();
    },
    onSuccess: (data: any) => toast({ title: "Remote scan complete", description: `${data.inventory?.totalFiles ?? 0} files indexed, ${data.inventory?.languages?.length ?? 0} languages detected` }),
    onError: (err: Error) => {
      const msg = err.message.replace(/^\d+:\s*/, "");
      try { const parsed = JSON.parse(msg); toast({ title: "Remote scan failed", description: parsed.error || msg, variant: "destructive" }); }
      catch { toast({ title: "Remote scan failed", description: msg, variant: "destructive" }); }
    },
  });

  const containerScanMutation = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("POST", `/api/container-scan`, { image: containerImage, tag: containerTag });
      return res.json();
    },
    onSuccess: (data: any) => toast({ title: "Container scan complete", description: data.available ? `${data.totalVulnerabilities ?? 0} vulnerabilities found` : (data.error || "Trivy not available") }),
    onError: (err: Error) => toast({ title: "Container scan failed", description: err.message, variant: "destructive" }),
  });

  const infraScanMutation = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("POST", `/api/repo-connections/${repo.id}/infra-scan`, { localPath: localPath || undefined });
      return res.json();
    },
    onSuccess: (data: any) => toast({ title: "IaC scan complete", description: `${data.totalFindings ?? 0} findings in ${data.filesScanned ?? 0} files` }),
    onError: (err: Error) => toast({ title: "IaC scan failed", description: err.message, variant: "destructive" }),
  });

  const displayResult = scanResult || (scanHistory && scanHistory.length > 0 ? scanHistory[0] : null);

  return (
    <div className="space-y-6">
      {/* Header */}
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

      {/* Status cards */}
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

      {/* Scan tabs */}
      <TabBar
        tabs={[
          { key: "api", label: "API Scan", icon: <Scan className="w-3.5 h-3.5" /> },
          { key: "local", label: "Local Scan", icon: <FolderSearch className="w-3.5 h-3.5" /> },
          { key: "cloud", label: "Cloud Scan", icon: <Shield className="w-3.5 h-3.5" /> },
        ]}
        active={scanTab}
        onChange={(key) => setScanTab(key as "api" | "local" | "cloud")}
      />

      {/* API Scan tab */}
      {scanTab === "api" && (
        <div className="space-y-4">
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
      )}

      {/* Local Scan tab */}
      {scanTab === "local" && (
        <div className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 pb-2">
              <CardTitle className="text-base">Run Local Scan</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-end gap-3 flex-wrap">
                <div className="space-y-2">
                  <Label className="text-xs">Scan Profile</Label>
                  <Select value={localProfile} onValueChange={(v) => setLocalProfile(v as ScanProfile)}>
                    <SelectTrigger className="w-[180px]" data-testid="select-local-profile">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {scanProfiles.map((p) => (
                        <SelectItem key={p.value} value={p.value}>
                          {p.label} — {p.description}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2 flex-1 min-w-[200px]">
                  <Label className="text-xs">Local Path (optional)</Label>
                  <Input
                    value={localPath}
                    onChange={(e) => setLocalPath(e.target.value)}
                    placeholder="Leave empty to clone automatically"
                    data-testid="input-local-path"
                  />
                </div>
                <Button
                  onClick={() => localScanMutation.mutate()}
                  disabled={localScanMutation.isPending}
                  data-testid="button-run-local-scan"
                >
                  <FolderSearch className="w-4 h-4 mr-1.5" />
                  {localScanMutation.isPending ? "Scanning..." : "Run Local Scan"}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Quick: inventory only. Safety: + sensitive paths, tool surfaces, CI checks. Deep: + secret detection, dependency analysis, license audit.
              </p>
            </CardContent>
          </Card>

          {localResult && (
            <div className="space-y-4">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <h3 className="text-base font-semibold flex items-center gap-2">
                  <FolderSearch className="w-4 h-4" />
                  Local Scan Results
                </h3>
                <div className="flex items-center gap-2">
                  <p className="text-xs text-muted-foreground">
                    {formatDate(localResult.scannedAt)} &middot; {localResult.profile} &middot; {localResult.duration}ms &middot; {localResult.commitSha.slice(0, 8)}
                  </p>
                  {localResult.artifactPath && (
                    <>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          window.open(`/api/repo-connections/${repo.id}/local-scans/${localResult.id}/artifacts/repo_scan.json`, "_blank");
                        }}
                        data-testid="button-download-artifact"
                      >
                        <Download className="w-3.5 h-3.5 mr-1" />
                        Export
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          window.open(`/api/repo-connections/${repo.id}/local-scans/${localResult.id}/artifacts/bundle.zip`, "_blank");
                        }}
                        data-testid="button-download-zip"
                      >
                        <Download className="w-3.5 h-3.5 mr-1" />
                        ZIP
                      </Button>
                    </>
                  )}
                </div>
              </div>

              <TabBar
                tabs={[
                  { key: "snapshot", label: "Snapshot" },
                  { key: "safety", label: "Safety Boundaries" },
                  { key: "security", label: "Security Signals" },
                ]}
                active={localResultTab}
                onChange={setLocalResultTab}
              />

              {localResultTab === "snapshot" && <InventoryPanel result={localResult} />}
              {localResultTab === "safety" && <SafetyPanel result={localResult} />}
              {localResultTab === "security" && <SecurityPanel result={localResult} />}
            </div>
          )}
        </div>
      )}

      {/* Cloud Scan tab */}
      {scanTab === "cloud" && (
        <div className="space-y-4">
          {!repo.accessToken && !repo.authProviderId && (
            <Card className="border-amber-200 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-950/20">
              <CardContent className="p-4 flex items-start gap-3">
                <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
                <div>
                  <p className="text-sm font-medium">Access token required for remote scanning</p>
                  <p className="text-xs text-muted-foreground mt-0.5">Remote scans and container scans need a PAT or linked auth provider to access the repository API. Add a token when editing this connection, or configure an auth provider in Settings &rarr; Authentication.</p>
                </div>
              </CardContent>
            </Card>
          )}
          <Card>
            <CardHeader className="pb-2 space-y-0">
              <CardTitle className="text-base">Remote Repository Scan</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-xs text-muted-foreground">Scan via the provider API without cloning. Detects languages, build systems, CI, frameworks, and sensitive paths.</p>
              <Button onClick={() => remoteScanMutation.mutate()} disabled={remoteScanMutation.isPending || (!repo.accessToken && !repo.authProviderId)} data-testid="button-remote-scan">
                <Scan className="w-4 h-4 mr-1.5" />
                {remoteScanMutation.isPending ? "Scanning..." : "Run Remote Scan"}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2 space-y-0">
              <CardTitle className="text-base">Container Image Scan</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-xs text-muted-foreground">Scan a container image for vulnerabilities using Trivy. Trivy must be installed locally.</p>
              <div className="flex items-end gap-3 flex-wrap">
                <div className="space-y-1 flex-1 min-w-[160px]">
                  <Label className="text-xs">Image</Label>
                  <Input value={containerImage} onChange={(e) => setContainerImage(e.target.value)} placeholder="e.g. nginx, myapp/server" data-testid="input-container-image" />
                </div>
                <div className="space-y-1 w-[100px]">
                  <Label className="text-xs">Tag</Label>
                  <Input value={containerTag} onChange={(e) => setContainerTag(e.target.value)} placeholder="latest" data-testid="input-container-tag" />
                </div>
                <Button onClick={() => containerScanMutation.mutate()} disabled={containerScanMutation.isPending || !containerImage} data-testid="button-container-scan">
                  <Shield className="w-4 h-4 mr-1.5" />
                  {containerScanMutation.isPending ? "Scanning..." : "Scan Image"}
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2 space-y-0">
              <CardTitle className="text-base">Infrastructure-as-Code Scan</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-xs text-muted-foreground">Analyze Terraform and CloudFormation files for security misconfigurations (public S3, open SGs, unencrypted storage, overly permissive IAM).</p>
              <Button onClick={() => infraScanMutation.mutate()} disabled={infraScanMutation.isPending} data-testid="button-infra-scan">
                <FileCode className="w-4 h-4 mr-1.5" />
                {infraScanMutation.isPending ? "Scanning..." : "Run IaC Scan"}
              </Button>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

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
            Connect repositories and scan for quality, safety, and security signals
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
              No repositories connected yet. Connect your first repository to start scanning.
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
