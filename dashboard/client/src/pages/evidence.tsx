import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiRequest } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import {
  FileJson, FileSpreadsheet, Package, Shield, ShieldCheck,
  AlertTriangle, CheckCircle, Download, RefreshCw, Copy,
  TrendingUp, Target, Eye, Cpu, Activity, Info, Lock
} from "lucide-react";

interface GovernanceScore {
  overall: number;
  autonomousRate: number;
  escalationRate: number;
  blockedHighRisk: number;
  policyCoverage: number;
  sessionCount: number;
  decisionCount: number;
  computedAt: string;
}

interface EvidenceBundleListItem {
  id: string;
  generatedAt: string;
  sessionId?: string;
  format: string;
  decisionCount: number;
  escalationCount: number;
  integrityStatus: string;
  governanceScore: number;
  manifestHash?: string;
}

interface IntegrityReport {
  overallStatus: string;
  lastVerifiedAt: string;
  components: { component: string; status: string; hash: string; lastChecked: string; details: string }[];
  hashChainValid: boolean;
  totalTraceEntries: number;
  traceHashSummary: string;
}

interface CompliancePack {
  id: string;
  name: string;
  framework: string;
  description: string;
  disclaimer: string;
  policies: { name: string; action: string; description: string }[];
}

function AnimatedRing({ value, max, size = 64, stroke = 5, color = "hsl(var(--primary))", label }: {
  value: number; max: number; size?: number; stroke?: number; color?: string; label?: string;
}) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.min(value / max, 1);
  const offset = circumference * (1 - pct);
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="hsl(var(--muted))" strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset 1.2s cubic-bezier(0.4, 0, 0.2, 1)" }}
        />
      </svg>
      {label && <span className="absolute text-[10px] font-semibold">{label}</span>}
    </div>
  );
}

function GovernanceScoreWidget({ score }: { score: GovernanceScore }) {
  const scoreColor = score.overall >= 80 ? "hsl(152, 69%, 31%)" : score.overall >= 60 ? "hsl(38, 92%, 50%)" : "hsl(0, 84%, 60%)";
  const metrics = [
    { icon: Cpu, label: "Autonomous", value: `${score.autonomousRate}%`, cls: "bg-blue-500/10 text-blue-600 dark:text-blue-400" },
    { icon: AlertTriangle, label: "Escalation Rate", value: `${score.escalationRate}%`, cls: "bg-amber-500/10 text-amber-600 dark:text-amber-400" },
    { icon: Shield, label: "Blocked High-Risk", value: String(score.blockedHighRisk), cls: "bg-red-500/10 text-red-600 dark:text-red-400" },
    { icon: Target, label: "Policy Coverage", value: `${score.policyCoverage}%`, cls: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" },
  ];

  return (
    <Card data-testid="governance-score-widget">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-primary" />Governance Score
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-5">
          <AnimatedRing value={score.overall} max={100} size={80} stroke={6} label={`${score.overall}`} color={scoreColor} />
          <div className="space-y-1">
            <p className="text-sm font-medium">Overall Score</p>
            <p className="text-xs text-muted-foreground">{score.sessionCount} sessions, {score.decisionCount} decisions</p>
            <p className="text-[10px] text-muted-foreground">Computed: {new Date(score.computedAt).toLocaleString()}</p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2.5">
          {metrics.map(m => (
            <div key={m.label} className="p-2.5 rounded-md bg-muted/50 flex items-center gap-2.5">
              <div className={`p-1.5 rounded ${m.cls}`}><m.icon className="w-3 h-3" /></div>
              <div>
                <p className="text-[10px] text-muted-foreground">{m.label}</p>
                <p className="text-sm font-semibold">{m.value}</p>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function IntegrityWidget({ report }: { report: IntegrityReport }) {
  return (
    <Card data-testid="integrity-widget">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-primary" />Integrity Verification
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-3">
          {report.overallStatus === "Verified"
            ? <CheckCircle className="w-7 h-7 text-emerald-600 dark:text-emerald-400" />
            : <AlertTriangle className="w-7 h-7 text-amber-600 dark:text-amber-400" />}
          <div>
            <p className="text-sm font-medium">{report.overallStatus}</p>
            <p className="text-xs text-muted-foreground">Hash chain: {report.hashChainValid ? "Valid" : "Invalid"}</p>
          </div>
        </div>
        <div className="space-y-1.5 text-xs">
          {report.components.map(c => (
            <div key={c.component} className="flex items-center justify-between">
              <span className="text-muted-foreground">{c.component}</span>
              <Badge variant="secondary" className={`text-[9px] ${c.status === "Verified" ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : "bg-amber-500/10 text-amber-700 dark:text-amber-300"}`}>
                {c.status}
              </Badge>
            </div>
          ))}
        </div>
        <div className="p-2 rounded bg-muted/50 text-xs">
          <p className="text-muted-foreground">Trace entries: {report.totalTraceEntries}</p>
          <p className="text-muted-foreground truncate">Summary hash: {report.traceHashSummary.slice(0, 24)}...</p>
        </div>
      </CardContent>
    </Card>
  );
}

function ExportPanel({ sessionFilter }: { sessionFilter?: string }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [exporting, setExporting] = useState<string | null>(null);

  const handleExportJSON = async () => {
    setExporting("json");
    try {
      const url = sessionFilter ? `/api/evidence/export/json?sessionId=${sessionFilter}` : "/api/evidence/export/json";
      const res = await fetch(url);
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `evidence-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
      toast({ title: "Evidence exported", description: "JSON evidence file downloaded" });
    } catch {
      toast({ title: "Export failed", variant: "destructive" });
    }
    setExporting(null);
  };

  const handleExportCSV = async () => {
    setExporting("csv");
    try {
      const url = sessionFilter ? `/api/evidence/export/csv?sessionId=${sessionFilter}` : "/api/evidence/export/csv";
      const res = await fetch(url);
      const text = await res.text();
      const blob = new Blob([text], { type: "text/csv" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `decisions-${Date.now()}.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
      toast({ title: "Evidence exported", description: "CSV decisions file downloaded" });
    } catch {
      toast({ title: "Export failed", variant: "destructive" });
    }
    setExporting(null);
  };

  const handleExportBundle = async () => {
    setExporting("bundle");
    try {
      const url = sessionFilter ? `/api/evidence/export/bundle?sessionId=${sessionFilter}` : "/api/evidence/export/bundle";
      const res = await fetch(url);
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `evidence-bundle-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
      queryClient.invalidateQueries({ queryKey: ["/api/evidence/bundles"] });
      toast({ title: "Bundle generated", description: `Bundle ${data.bundleId} created and downloaded` });
    } catch {
      toast({ title: "Export failed", variant: "destructive" });
    }
    setExporting(null);
  };

  return (
    <Card data-testid="export-panel">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Download className="w-4 h-4 text-primary" />Export Evidence
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">
          Generate verifiable governance evidence from local decision logs, traces, and integrity data.
          All exports are sanitized — secrets and tokens are automatically redacted.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
          <Button variant="outline" className="h-auto py-3 flex flex-col gap-1.5" onClick={handleExportJSON} disabled={!!exporting} data-testid="button-export-json">
            <FileJson className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            <span className="text-xs font-medium">JSON Export</span>
            <span className="text-[10px] text-muted-foreground">Full evidence data</span>
            {exporting === "json" && <RefreshCw className="w-3 h-3 animate-spin" />}
          </Button>
          <Button variant="outline" className="h-auto py-3 flex flex-col gap-1.5" onClick={handleExportCSV} disabled={!!exporting} data-testid="button-export-csv">
            <FileSpreadsheet className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
            <span className="text-xs font-medium">CSV Export</span>
            <span className="text-[10px] text-muted-foreground">Decisions & escalations</span>
            {exporting === "csv" && <RefreshCw className="w-3 h-3 animate-spin" />}
          </Button>
          <Button variant="outline" className="h-auto py-3 flex flex-col gap-1.5" onClick={handleExportBundle} disabled={!!exporting} data-testid="button-export-bundle">
            <Package className="w-5 h-5 text-purple-600 dark:text-purple-400" />
            <span className="text-xs font-medium">Full Bundle</span>
            <span className="text-[10px] text-muted-foreground">Hash-verified package</span>
            {exporting === "bundle" && <RefreshCw className="w-3 h-3 animate-spin" />}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function BundlesList() {
  const { data: bundles, isLoading } = useQuery<EvidenceBundleListItem[]>({ queryKey: ["/api/evidence/bundles"] });
  const { toast } = useToast();

  if (isLoading) return <Skeleton className="h-40 w-full" />;

  return (
    <Card data-testid="bundles-list">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Package className="w-4 h-4 text-primary" />Generated Evidence Bundles
        </CardTitle>
      </CardHeader>
      <CardContent>
        {(!bundles || bundles.length === 0) && (
          <p className="text-xs text-muted-foreground py-4 text-center">No evidence bundles generated yet.</p>
        )}
        {bundles && bundles.length > 0 && (
          <div className="space-y-2">
            {bundles.map(b => (
              <div key={b.id} className="flex items-center justify-between gap-3 p-3 rounded-md border bg-card hover:bg-muted/30 transition-colors" data-testid={`bundle-${b.id}`}>
                <div className="flex items-center gap-3 min-w-0">
                  <div className={`p-1.5 rounded ${b.integrityStatus === "Verified" ? "bg-emerald-500/10 text-emerald-600" : "bg-amber-500/10 text-amber-600"}`}>
                    {b.integrityStatus === "Verified" ? <CheckCircle className="w-3.5 h-3.5" /> : <AlertTriangle className="w-3.5 h-3.5" />}
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-medium truncate">{b.id}</p>
                    <p className="text-[10px] text-muted-foreground">
                      {new Date(b.generatedAt).toLocaleDateString()} · {b.decisionCount} decisions · {b.escalationCount} escalations
                      {b.sessionId && ` · Session: ${b.sessionId}`}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Badge variant="secondary" className="text-[9px]">Score: {b.governanceScore}</Badge>
                  <Badge variant="secondary" className="text-[9px]">{b.format.toUpperCase()}</Badge>
                  {b.manifestHash && (
                    <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => {
                      navigator.clipboard.writeText(b.manifestHash || "");
                      toast({ title: "Copied", description: "Manifest hash copied to clipboard" });
                    }} data-testid={`copy-hash-${b.id}`}>
                      <Copy className="w-3 h-3" />
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function CompliancePacksPanel() {
  const { data: packs, isLoading } = useQuery<CompliancePack[]>({ queryKey: ["/api/evidence/packs"] });
  const [expanded, setExpanded] = useState<string | null>(null);

  if (isLoading) return <Skeleton className="h-40 w-full" />;

  return (
    <Card data-testid="compliance-packs">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Lock className="w-4 h-4 text-primary" />Policy Pack Templates
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2.5">
        <p className="text-xs text-muted-foreground">
          Pre-configured policy bundles that support governance evidence collection.
          These are policy presets, not compliance certifications.
        </p>
        {packs && packs.map(pack => (
          <div key={pack.id} className="border rounded-md overflow-hidden" data-testid={`pack-${pack.id}`}>
            <button
              className="w-full text-left p-3 hover:bg-muted/30 transition-colors flex items-center justify-between gap-2"
              onClick={() => setExpanded(prev => prev === pack.id ? null : pack.id)}
              data-testid={`button-pack-${pack.id}`}
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <Badge variant="secondary" className="text-[9px] shrink-0">{pack.framework}</Badge>
                <span className="text-xs font-medium truncate">{pack.name}</span>
              </div>
              <Activity className={`w-3.5 h-3.5 text-muted-foreground transition-transform ${expanded === pack.id ? "rotate-90" : ""}`} />
            </button>
            {expanded === pack.id && (
              <div className="px-3 pb-3 space-y-2.5 border-t pt-2.5">
                <p className="text-xs text-muted-foreground">{pack.description}</p>
                <div className="bg-amber-500/5 border border-amber-500/20 rounded p-2 flex items-start gap-2">
                  <Info className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
                  <p className="text-[10px] text-amber-700 dark:text-amber-300">{pack.disclaimer}</p>
                </div>
                <div className="space-y-1.5">
                  {pack.policies.map(p => (
                    <div key={p.name} className="flex items-center gap-2 text-xs">
                      <Badge variant="secondary" className={`text-[9px] shrink-0 ${p.action === "enforce" ? "bg-blue-500/10 text-blue-700 dark:text-blue-300" : p.action === "require_human" ? "bg-amber-500/10 text-amber-700 dark:text-amber-300" : "bg-muted"}`}>
                        {p.action}
                      </Badge>
                      <span className="text-muted-foreground truncate">{p.description}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export default function EvidencePage() {
  const { data: score, isLoading: scoreLoading } = useQuery<GovernanceScore>({ queryKey: ["/api/evidence/score"] });
  const { data: integrityReport, isLoading: integrityLoading } = useQuery<IntegrityReport>({ queryKey: ["/api/evidence/integrity"] });
  const { data: sessions } = useQuery<{ id: string; tool: string; status: string }[]>({ queryKey: ["/api/sessions"] });
  const [sessionFilter, setSessionFilter] = useState<string>("");
  const [activeTab, setActiveTab] = useState("overview");

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Governance Evidence</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Export verifiable governance evidence from local decision data
        </p>
      </div>

      <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-3 flex items-start gap-2.5" data-testid="evidence-disclaimer">
        <Info className="w-4 h-4 text-blue-600 dark:text-blue-400 mt-0.5 shrink-0" />
        <div>
          <p className="text-xs font-medium text-blue-700 dark:text-blue-300">Governance Evidence Disclaimer</p>
          <p className="text-[11px] text-blue-600/80 dark:text-blue-400/80 mt-0.5">
            AtlasBridge produces verifiable governance evidence; it does not certify compliance.
            Users are responsible for their own compliance programs. Evidence exports are deterministic
            and reproducible from local decision logs, traces, and integrity verification data.
          </p>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="w-full justify-start">
          <TabsTrigger value="overview" data-testid="tab-evidence-overview">Overview</TabsTrigger>
          <TabsTrigger value="export" data-testid="tab-evidence-export">Export</TabsTrigger>
          <TabsTrigger value="bundles" data-testid="tab-evidence-bundles">Bundles</TabsTrigger>
          <TabsTrigger value="packs" data-testid="tab-evidence-packs">Policy Packs</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {scoreLoading || !score ? <Skeleton className="h-52" /> : <GovernanceScoreWidget score={score} />}
            {integrityLoading || !integrityReport ? <Skeleton className="h-52" /> : <IntegrityWidget report={integrityReport} />}
          </div>

          <Card data-testid="replay-references">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Eye className="w-4 h-4 text-primary" />Replay References
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground mb-3">Session IDs available for evidence export and replay reconstruction.</p>
              {(!sessions || sessions.length === 0) ? (
                <p className="text-xs text-muted-foreground py-2 text-center">No sessions recorded yet.</p>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
                  {sessions.map(s => (
                    <div key={s.id} className="flex items-center gap-2 p-2 rounded-md bg-muted/50 text-xs" data-testid={`replay-ref-${s.id}`}>
                      <div className="min-w-0 flex-1">
                        <code className="font-mono text-[10px] truncate block">{s.id}</code>
                        <span className="text-[9px] text-muted-foreground truncate block">{s.tool} · {s.status}</span>
                      </div>
                      <Button variant="ghost" size="icon" className="h-5 w-5 shrink-0" onClick={() => navigator.clipboard.writeText(s.id)} data-testid={`copy-session-${s.id}`}>
                        <Copy className="w-2.5 h-2.5" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="export" className="space-y-4 mt-4">
          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center gap-3 flex-wrap">
                <label className="text-xs font-medium text-muted-foreground">Filter by session (optional):</label>
                <Select value={sessionFilter} onValueChange={setSessionFilter}>
                  <SelectTrigger className="w-64 h-8 text-xs" data-testid="select-session-filter">
                    <SelectValue placeholder="All sessions" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All sessions</SelectItem>
                    {sessions?.map(s => (
                      <SelectItem key={s.id} value={s.id}>{s.id} ({s.tool})</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>
          <ExportPanel sessionFilter={sessionFilter && sessionFilter !== "all" ? sessionFilter : undefined} />
        </TabsContent>

        <TabsContent value="bundles" className="mt-4">
          <BundlesList />
        </TabsContent>

        <TabsContent value="packs" className="mt-4">
          <CompliancePacksPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}
