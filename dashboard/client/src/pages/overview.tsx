import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "wouter";
import type { OverviewData, MetricInsight } from "@shared/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { riskBg, integrityColor, formatTimestamp, timeAgo } from "@/lib/utils";
import {
  MonitorDot, Clock, TrendingUp, Cpu, AlertTriangle,
  ShieldCheck, Activity, Brain, Shield, Gauge, X,
  ArrowUpRight, ArrowDownRight, Minus, Lightbulb,
  CheckCircle, XCircle, ChevronRight, Zap, Target, Eye, FileCheck
} from "lucide-react";

function AnimatedRing({ value, max, size = 64, stroke = 5, color = "hsl(var(--primary))", trackColor = "hsl(var(--muted))", label, animate = true }: {
  value: number; max: number; size?: number; stroke?: number; color?: string; trackColor?: string; label?: string; animate?: boolean;
}) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.min(value / max, 1);
  const offset = circumference * (1 - pct);
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={trackColor} strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={offset}
          style={animate ? { transition: "stroke-dashoffset 1.2s cubic-bezier(0.4, 0, 0.2, 1)" } : undefined}
        />
      </svg>
      {label && <span className="absolute text-[10px] font-semibold">{label}</span>}
    </div>
  );
}

function TrendIndicator({ trend }: { trend: "improving" | "stable" | "declining" }) {
  if (trend === "improving") return <span className="flex items-center gap-0.5 text-emerald-600 dark:text-emerald-400 text-[10px] font-medium"><ArrowUpRight className="w-3 h-3" />Improving</span>;
  if (trend === "declining") return <span className="flex items-center gap-0.5 text-red-600 dark:text-red-400 text-[10px] font-medium"><ArrowDownRight className="w-3 h-3" />Declining</span>;
  return <span className="flex items-center gap-0.5 text-muted-foreground text-[10px] font-medium"><Minus className="w-3 h-3" />Stable</span>;
}

function InsightCard({ insight, onClose }: { insight: MetricInsight; onClose?: () => void }) {
  const typeStyles = {
    positive: "border-l-emerald-500 bg-emerald-500/5",
    warning: "border-l-amber-500 bg-amber-500/5",
    recommendation: "border-l-blue-500 bg-blue-500/5",
  };
  const typeIcons = {
    positive: <CheckCircle className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />,
    warning: <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />,
    recommendation: <Lightbulb className="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0" />,
  };
  return (
    <div className={`rounded-md border-l-[3px] p-3 ${typeStyles[insight.type]} transition-all duration-300`} data-testid={`insight-${insight.id}`}>
      <div className="flex items-start gap-2.5">
        {typeIcons[insight.type]}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-medium">{insight.title}</p>
            <div className="flex items-center gap-1.5 shrink-0">
              <Badge variant="secondary" className={`text-[9px] ${insight.impact === "high" ? "bg-red-500/10 text-red-700 dark:text-red-300" : insight.impact === "medium" ? "bg-amber-500/10 text-amber-700 dark:text-amber-300" : "bg-muted"}`}>{insight.impact}</Badge>
              {onClose && <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X className="w-3 h-3" /></button>}
            </div>
          </div>
          <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{insight.description}</p>
          {insight.actionable && (
            <Badge variant="secondary" className="text-[9px] mt-2 bg-primary/10 text-primary cursor-pointer" data-testid={`insight-action-${insight.id}`}>
              <Zap className="w-2.5 h-2.5 mr-0.5" />Take Action
            </Badge>
          )}
        </div>
      </div>
    </div>
  );
}

function SafetyMetricItem({ icon: IconComp, label, value, cls }: { icon: React.ElementType; label: string; value: string; cls: string }) {
  return (
    <div className="p-2.5 rounded-md bg-muted/50 flex items-center gap-2.5">
      <div className={`p-1.5 rounded ${cls}`}><IconComp className="w-3 h-3" /></div>
      <div>
        <p className="text-[10px] text-muted-foreground">{label}</p>
        <p className="text-sm font-semibold">{value}</p>
      </div>
    </div>
  );
}

type PanelId = "sessions" | "safety" | "compliance" | "risk" | "operations" | "integrity" | null;

function StatCard3D({ title, value, subtitle, icon: Icon, variant, onClick, active, children }: {
  title: string; value: string | number; subtitle?: string;
  icon: React.ElementType; variant?: string; onClick?: () => void; active?: boolean; children?: React.ReactNode;
}) {
  return (
    <div className="group" style={{ perspective: "800px" }}>
      <Card
        className={`cursor-pointer stat-card-3d ${active ? "ring-2 ring-primary shadow-lg" : ""}`}
        onClick={onClick}
        style={{ transformStyle: "preserve-3d" }}
        data-testid={`stat-card-${title.toLowerCase().replace(/\s/g, "-")}`}
      >
        <CardContent className="p-4">
          <div className="flex items-start justify-between gap-1">
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground font-medium">{title}</p>
              <p className="text-2xl font-semibold tracking-tight" data-testid={`stat-${title.toLowerCase().replace(/\s/g, "-")}`}>
                {value}
              </p>
              {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
            </div>
            <div className={`p-2 rounded-md transition-transform duration-300 group-hover:scale-110 ${variant || "bg-primary/10 text-primary"}`}>
              <Icon className="w-4 h-4" />
            </div>
          </div>
          {children}
          <div className="flex items-center gap-1 mt-2 text-[10px] text-muted-foreground">
            <ChevronRight className={`w-3 h-3 transition-transform duration-200 ${active ? "rotate-90" : ""}`} />
            <span>{active ? "Click to close" : "Click to explore"}</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function ActiveSessionsPanel({ data }: { data: OverviewData }) {
  const running = data.activeSessions;
  const total = 8;
  return (
    <Card className="animate-in slide-in-from-top-2 duration-300">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2"><MonitorDot className="w-4 h-4 text-primary" />Active Sessions Detail</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-4">
          <AnimatedRing value={running} max={total} size={72} stroke={6} label={`${running}/${total}`} color="hsl(186, 70%, 32%)" />
          <div>
            <p className="text-sm font-medium">{running} of {total} sessions active</p>
            <p className="text-xs text-muted-foreground mt-0.5">{total - running} stopped or paused</p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="p-2.5 rounded-md bg-muted/50">
            <p className="text-[10px] text-muted-foreground">Avg Duration</p>
            <p className="text-sm font-medium mt-0.5">4.2h</p>
          </div>
          <div className="p-2.5 rounded-md bg-muted/50">
            <p className="text-[10px] text-muted-foreground">Tools Active</p>
            <p className="text-sm font-medium mt-0.5">6 tools</p>
          </div>
        </div>
        {data.insights.filter(i => i.category === "operations").map(i => <InsightCard key={i.id} insight={i} />)}
      </CardContent>
    </Card>
  );
}

function AISafetyPanel({ data }: { data: OverviewData }) {
  const s = data.aiSafety;
  const trustColor = s.modelTrustScore >= 90 ? "hsl(152, 69%, 31%)" : s.modelTrustScore >= 70 ? "hsl(38, 92%, 50%)" : "hsl(0, 84%, 60%)";
  return (
    <Card className="animate-in slide-in-from-top-2 duration-300">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2"><Brain className="w-4 h-4 text-primary" />AI Safety Dashboard</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-5">
          <AnimatedRing value={s.modelTrustScore} max={100} size={80} stroke={6} label={`${s.modelTrustScore}%`} color={trustColor} />
          <div className="space-y-1.5">
            <p className="text-sm font-medium">Model Trust Score</p>
            <TrendIndicator trend={s.trend} />
            <p className="text-xs text-muted-foreground">Avg confidence: {(s.avgConfidence * 100).toFixed(0)}%</p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2.5">
          <SafetyMetricItem icon={Shield} label="Injections Blocked" value={String(s.promptInjectionBlocked)} cls="bg-red-500/10 text-red-600 dark:text-red-400" />
          <SafetyMetricItem icon={Eye} label="Hallucination Rate" value={`${s.hallucinationRate}%`} cls="bg-amber-500/10 text-amber-600 dark:text-amber-400" />
          <SafetyMetricItem icon={Target} label="Bias Detections" value={String(s.biasDetections)} cls="bg-purple-500/10 text-purple-600 dark:text-purple-400" />
          <SafetyMetricItem icon={Cpu} label="Human Overrides" value={`${s.humanOverrideRate}%`} cls="bg-blue-500/10 text-blue-600 dark:text-blue-400" />
        </div>
        {data.insights.filter(i => i.category === "safety").map(i => <InsightCard key={i.id} insight={i} />)}
      </CardContent>
    </Card>
  );
}

function CompliancePanel({ data }: { data: OverviewData }) {
  const c = data.compliance;
  const scoreColor = c.overallScore >= 90 ? "hsl(152, 69%, 31%)" : c.overallScore >= 70 ? "hsl(38, 92%, 50%)" : "hsl(0, 84%, 60%)";
  return (
    <Card className="animate-in slide-in-from-top-2 duration-300">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2"><Shield className="w-4 h-4 text-primary" />Compliance Overview</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-5">
          <AnimatedRing value={c.overallScore} max={100} size={80} stroke={6} label={`${c.overallScore}%`} color={scoreColor} />
          <div className="space-y-1">
            <p className="text-sm font-medium">Overall Compliance</p>
            <p className="text-xs text-muted-foreground">Policy adherence: {c.policyAdherence}%</p>
            <p className="text-xs text-muted-foreground">Next audit: {c.nextAuditDays} days</p>
          </div>
        </div>
        <div className="space-y-2.5">
          <p className="text-xs font-medium text-muted-foreground">Framework Scores</p>
          {c.frameworkScores.map(fw => {
            const pct = (fw.score / fw.maxScore) * 100;
            return (
              <div key={fw.framework} data-testid={`compliance-${fw.framework.toLowerCase()}`}>
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="text-xs font-medium">{fw.framework}</span>
                  <span className="text-xs text-muted-foreground">{fw.score}/{fw.maxScore}</span>
                </div>
                <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                  <div className={`h-full rounded-full transition-all duration-1000 ${pct >= 90 ? "bg-emerald-500" : pct >= 70 ? "bg-amber-500" : "bg-red-500"}`} style={{ width: `${pct}%` }} />
                </div>
              </div>
            );
          })}
        </div>
        <div className="grid grid-cols-2 gap-2.5">
          <div className="p-2.5 rounded-md bg-muted/50">
            <p className="text-[10px] text-muted-foreground">Open Findings</p>
            <p className="text-sm font-semibold text-amber-600 dark:text-amber-400">{c.openFindings}</p>
          </div>
          <div className="p-2.5 rounded-md bg-muted/50">
            <p className="text-[10px] text-muted-foreground">Resolved (30d)</p>
            <p className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">{c.resolvedLast30d}</p>
          </div>
        </div>
        {data.insights.filter(i => i.category === "compliance").map(i => <InsightCard key={i.id} insight={i} />)}
      </CardContent>
    </Card>
  );
}

function RiskPanel({ data }: { data: OverviewData }) {
  const total = data.riskBreakdown.low + data.riskBreakdown.medium + data.riskBreakdown.high + data.riskBreakdown.critical;
  const levels = [
    { key: "critical" as const, color: "bg-red-500", label: "Critical" },
    { key: "high" as const, color: "bg-orange-500", label: "High" },
    { key: "medium" as const, color: "bg-amber-500", label: "Medium" },
    { key: "low" as const, color: "bg-emerald-500", label: "Low" },
  ];
  return (
    <Card className="animate-in slide-in-from-top-2 duration-300">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-primary" />Risk Analysis</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-1 h-3 rounded-full overflow-hidden">
          {levels.map(l => {
            const pct = total > 0 ? (data.riskBreakdown[l.key] / total) * 100 : 0;
            return pct > 0 ? <div key={l.key} className={`${l.color} transition-all duration-1000`} style={{ width: `${pct}%` }} /> : null;
          })}
        </div>
        <div className="grid grid-cols-2 gap-2.5">
          {levels.map(l => (
            <div key={l.key} className="flex items-center gap-2 p-2 rounded-md bg-muted/50">
              <span className={`w-2.5 h-2.5 rounded-full ${l.color} shrink-0`} />
              <div>
                <p className="text-[10px] text-muted-foreground">{l.label}</p>
                <p className="text-sm font-semibold">{data.riskBreakdown[l.key]}</p>
              </div>
            </div>
          ))}
        </div>
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-2">Top Rules Triggered</p>
          {data.topRulesTriggered.slice(0, 3).map(rule => (
            <div key={rule.ruleId} className="flex items-center justify-between gap-2 py-1.5 text-xs">
              <span className="truncate">{rule.ruleName}</span>
              <Badge variant="secondary" className="text-[10px] shrink-0">{rule.count}x</Badge>
            </div>
          ))}
        </div>
        {data.insights.filter(i => i.category === "risk").map(i => <InsightCard key={i.id} insight={i} />)}
      </CardContent>
    </Card>
  );
}

function OperationsPanel({ data }: { data: OverviewData }) {
  const o = data.operational;
  return (
    <Card className="animate-in slide-in-from-top-2 duration-300">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2"><Gauge className="w-4 h-4 text-primary" />Operational Health</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-5">
          <AnimatedRing value={o.uptime} max={100} size={72} stroke={6} label={`${o.uptime}%`} color="hsl(152, 69%, 31%)" />
          <div>
            <p className="text-sm font-medium">System Uptime</p>
            <p className="text-xs text-muted-foreground">Error rate: {o.errorRate}%</p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2.5">
          {[
            ["Avg Response", `${o.avgResponseTime}ms`],
            ["P95 Latency", `${o.p95Latency}ms`],
            ["Throughput", `${o.throughput}/hr`],
            ["Integrations", String(o.activeIntegrations)],
          ].map(([label, val]) => (
            <div key={String(label)} className="p-2.5 rounded-md bg-muted/50">
              <p className="text-[10px] text-muted-foreground">{String(label)}</p>
              <p className="text-sm font-semibold">{String(val)}</p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function IntegrityPanel({ data }: { data: OverviewData }) {
  return (
    <Card className="animate-in slide-in-from-top-2 duration-300">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2"><ShieldCheck className="w-4 h-4 text-primary" />Integrity Verification</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-3">
          {data.integrityStatus === "Verified" ? <CheckCircle className="w-8 h-8 text-emerald-600 dark:text-emerald-400" /> : data.integrityStatus === "Warning" ? <AlertTriangle className="w-8 h-8 text-amber-600 dark:text-amber-400" /> : <XCircle className="w-8 h-8 text-red-600 dark:text-red-400" />}
          <div>
            <p className="text-sm font-medium">{data.integrityStatus}</p>
            <p className="text-xs text-muted-foreground">All components hash-verified</p>
          </div>
        </div>
        <div className="text-xs text-muted-foreground space-y-1.5">
          <div className="flex justify-between"><span>Policy Engine</span><Badge variant="secondary" className="text-[9px] bg-emerald-500/10 text-emerald-700 dark:text-emerald-300">Verified</Badge></div>
          <div className="flex justify-between"><span>Decision Trace Store</span><Badge variant="secondary" className="text-[9px] bg-emerald-500/10 text-emerald-700 dark:text-emerald-300">Verified</Badge></div>
          <div className="flex justify-between"><span>Prompt Resolver</span><Badge variant="secondary" className="text-[9px] bg-amber-500/10 text-amber-700 dark:text-amber-300">Warning</Badge></div>
          <div className="flex justify-between"><span>Audit Logger</span><Badge variant="secondary" className="text-[9px] bg-emerald-500/10 text-emerald-700 dark:text-emerald-300">Verified</Badge></div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function OverviewPage() {
  const { data, isLoading } = useQuery<OverviewData>({ queryKey: ["/api/overview"] });
  const [activePanel, setActivePanel] = useState<PanelId>(null);

  const toggle = (id: PanelId) => setActivePanel(prev => prev === id ? null : id);

  if (isLoading || !data) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Overview</h1>
          <p className="text-sm text-muted-foreground mt-1">System status and recent activity</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Card key={i}><CardContent className="p-4"><Skeleton className="h-20 w-full" /></CardContent></Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Overview</h1>
        <p className="text-sm text-muted-foreground mt-1">System status, AI safety, and compliance</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <StatCard3D title="Active Sessions" value={data.activeSessions} subtitle={`${8 - data.activeSessions} idle`} icon={MonitorDot} onClick={() => toggle("sessions")} active={activePanel === "sessions"} />
        <StatCard3D title="AI Safety Score" value={`${data.aiSafety.modelTrustScore}%`} icon={Brain} variant="bg-purple-500/10 text-purple-600 dark:text-purple-400" onClick={() => toggle("safety")} active={activePanel === "safety"}>
          <TrendIndicator trend={data.aiSafety.trend} />
        </StatCard3D>
        <StatCard3D title="Compliance Score" value={`${data.compliance.overallScore}%`} subtitle={`${data.compliance.openFindings} open findings`} icon={Shield} variant="bg-blue-500/10 text-blue-600 dark:text-blue-400" onClick={() => toggle("compliance")} active={activePanel === "compliance"} />
        <StatCard3D
          title="High-Risk Events"
          value={data.highRiskEvents}
          subtitle={`Escalation rate: ${data.escalationRate}%`}
          icon={AlertTriangle}
          variant={data.highRiskEvents > 5 ? "bg-red-500/10 text-red-600 dark:text-red-400" : "bg-amber-500/10 text-amber-600 dark:text-amber-400"}
          onClick={() => toggle("risk")}
          active={activePanel === "risk"}
        />
        <StatCard3D title="System Health" value={`${data.operational.uptime}%`} subtitle={`${data.operational.avgResponseTime}ms avg`} icon={Gauge} variant="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" onClick={() => toggle("operations")} active={activePanel === "operations"} />
        <StatCard3D title="Integrity Status" value={data.integrityStatus} icon={ShieldCheck} variant={integrityColor(data.integrityStatus)} onClick={() => toggle("integrity")} active={activePanel === "integrity"} />
      </div>

      {activePanel && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {activePanel === "sessions" && <ActiveSessionsPanel data={data} />}
          {activePanel === "safety" && <AISafetyPanel data={data} />}
          {activePanel === "compliance" && <CompliancePanel data={data} />}
          {activePanel === "risk" && <RiskPanel data={data} />}
          {activePanel === "operations" && <OperationsPanel data={data} />}
          {activePanel === "integrity" && <IntegrityPanel data={data} />}

          <Card className="animate-in slide-in-from-top-2 duration-300">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Lightbulb className="w-4 h-4 text-primary" />Insights & Recommendations
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2.5">
              {data.insights
                .filter(i => activePanel === "risk" ? i.category === "risk" : activePanel === "safety" ? i.category === "safety" : activePanel === "compliance" ? i.category === "compliance" : activePanel === "operations" ? i.category === "operations" : true)
                .map(i => <InsightCard key={i.id} insight={i} />)
              }
              {data.insights.filter(i => activePanel === "risk" ? i.category === "risk" : activePanel === "safety" ? i.category === "safety" : activePanel === "compliance" ? i.category === "compliance" : activePanel === "operations" ? i.category === "operations" : true).length === 0 && (
                <p className="text-xs text-muted-foreground py-4 text-center">No specific insights for this metric</p>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Activity className="w-4 h-4 text-primary" />Recent Activity
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="max-h-[360px] overflow-auto">
              {data.recentActivity.slice(0, 10).map((event, i) => (
                <div key={event.id} className={`flex items-start gap-3 px-4 py-2.5 transition-colors hover:bg-muted/30 ${i !== Math.min(data.recentActivity.length, 10) - 1 ? "border-b" : ""}`} data-testid={`activity-event-${event.id}`}>
                  <div className="mt-1.5 flex-shrink-0">
                    <span className={`inline-block w-2 h-2 rounded-full ${
                      event.riskLevel === "critical" ? "bg-red-500" :
                      event.riskLevel === "high" ? "bg-orange-500" :
                      event.riskLevel === "medium" ? "bg-amber-500" : "bg-emerald-500"
                    }`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm">{event.message}</p>
                    <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                      <span className="text-[10px] text-muted-foreground">{timeAgo(event.timestamp)}</span>
                      <Badge variant="secondary" className="text-[9px] px-1.5 py-0">{event.type}</Badge>
                      {event.sessionId && <span className="text-[10px] text-muted-foreground font-mono">{event.sessionId}</span>}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Quick Metrics</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between p-2.5 rounded-md bg-muted/50">
              <div className="flex items-center gap-2">
                <Brain className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400" />
                <span className="text-xs">Avg Confidence</span>
              </div>
              <span className="text-sm font-semibold">{(data.aiSafety.avgConfidence * 100).toFixed(0)}%</span>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded-md bg-muted/50">
              <div className="flex items-center gap-2">
                <Shield className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
                <span className="text-xs">Policy Adherence</span>
              </div>
              <span className="text-sm font-semibold">{data.compliance.policyAdherence}%</span>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded-md bg-muted/50">
              <div className="flex items-center gap-2">
                <Cpu className="w-3.5 h-3.5 text-primary" />
                <span className="text-xs">Autonomy Mode</span>
              </div>
              <Badge variant="secondary" className="text-[10px]">{data.autonomyMode}</Badge>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded-md bg-muted/50">
              <div className="flex items-center gap-2">
                <Clock className="w-3.5 h-3.5 text-muted-foreground" />
                <span className="text-xs">Last Event</span>
              </div>
              <span className="text-[10px] text-muted-foreground">{timeAgo(data.lastEventTimestamp)}</span>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded-md bg-muted/50">
              <div className="flex items-center gap-2">
                <Zap className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
                <span className="text-xs">Throughput</span>
              </div>
              <span className="text-sm font-semibold">{data.operational.throughput}/hr</span>
            </div>
            <Link href="/evidence">
              <div className="flex items-center justify-between p-2.5 rounded-md bg-primary/5 border border-primary/10 cursor-pointer hover:bg-primary/10 transition-colors" data-testid="link-governance-evidence">
                <div className="flex items-center gap-2">
                  <FileCheck className="w-3.5 h-3.5 text-primary" />
                  <span className="text-xs font-medium">Governance Evidence</span>
                </div>
                <ChevronRight className="w-3 h-3 text-muted-foreground" />
              </div>
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
