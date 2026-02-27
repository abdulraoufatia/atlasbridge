import { useQuery, useMutation } from "@tanstack/react-query";
import { useState, useEffect, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { useToast } from "@/hooks/use-toast";
import { apiRequest, queryClient } from "@/lib/queryClient";
import type { Session, AgentTurn, AgentPlan, AgentToolRun, AgentState, AgentDecision } from "@shared/schema";
import {
  Sparkles, Send, ChevronDown, Clock, Wrench, ShieldCheck, ShieldAlert,
  CheckCircle, XCircle, AlertTriangle, Loader2, Copy, Play, Square, Plus
} from "lucide-react";
import { Label } from "@/components/ui/label";

function ago(d: string): string {
  const diff = Date.now() - new Date(d).getTime();
  if (diff < 60000) return "just now";
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  return `${Math.floor(diff / 3600000)}h ago`;
}

function stateBadge(state: string) {
  const map: Record<string, { cls: string; icon: typeof Loader2 }> = {
    ready: { cls: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300", icon: CheckCircle },
    intake: { cls: "bg-blue-500/10 text-blue-700 dark:text-blue-300", icon: Loader2 },
    plan: { cls: "bg-violet-500/10 text-violet-700 dark:text-violet-300", icon: Loader2 },
    gate: { cls: "bg-amber-500/10 text-amber-700 dark:text-amber-300", icon: ShieldAlert },
    execute: { cls: "bg-orange-500/10 text-orange-700 dark:text-orange-300", icon: Play },
    synthesise: { cls: "bg-indigo-500/10 text-indigo-700 dark:text-indigo-300", icon: Loader2 },
    respond: { cls: "bg-cyan-500/10 text-cyan-700 dark:text-cyan-300", icon: Loader2 },
    stopped: { cls: "bg-gray-500/10 text-gray-700 dark:text-gray-300", icon: Square },
  };
  const info = map[state] || map.ready;
  const Icon = info.icon;
  return (
    <Badge variant="secondary" className={`text-[10px] gap-1 ${info.cls}`}>
      <Icon className="w-3 h-3" />
      {state.toUpperCase()}
    </Badge>
  );
}

function riskBadge(level: string) {
  const cls: Record<string, string> = {
    low: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    medium: "bg-amber-500/10 text-amber-700 dark:text-amber-300",
    high: "bg-red-500/10 text-red-700 dark:text-red-300",
  };
  return (
    <Badge variant="secondary" className={`text-[10px] ${cls[level] || cls.low}`}>
      {level}
    </Badge>
  );
}

function PlanCard({
  plan,
  sessionId,
  onAction,
}: {
  plan: AgentPlan;
  sessionId: string;
  onAction: () => void;
}) {
  const { toast } = useToast();

  const approveMutation = useMutation({
    mutationFn: () =>
      apiRequest("POST", `/api/agent/sessions/${sessionId}/approve`, { plan_id: plan.id }),
    onSuccess: () => {
      toast({ title: "Plan approved" });
      onAction();
    },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const denyMutation = useMutation({
    mutationFn: () =>
      apiRequest("POST", `/api/agent/sessions/${sessionId}/deny`, { plan_id: plan.id }),
    onSuccess: () => {
      toast({ title: "Plan denied" });
      onAction();
    },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  return (
    <div className="border rounded-lg p-3 space-y-2 bg-muted/30" data-testid={`plan-card-${plan.id}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-3.5 h-3.5 text-muted-foreground" />
          <span className="text-xs font-medium">Plan</span>
          {riskBadge(plan.risk_level)}
          <Badge variant="outline" className="text-[10px]">{plan.status}</Badge>
        </div>
        <code className="text-[10px] text-muted-foreground font-mono">{plan.id.slice(0, 8)}</code>
      </div>
      <p className="text-sm">{plan.description}</p>
      {plan.steps.length > 0 && (
        <Collapsible>
          <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors">
            <ChevronDown className="w-3 h-3" />
            {plan.steps.length} step{plan.steps.length !== 1 ? "s" : ""}
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="mt-2 space-y-1">
              {plan.steps.map((step, i) => (
                <div key={i} className="flex items-center gap-2 text-xs font-mono bg-muted/50 rounded px-2 py-1">
                  <Wrench className="w-3 h-3 text-muted-foreground shrink-0" />
                  <span className="font-medium">{step.tool}</span>
                  <span className="text-muted-foreground truncate">{step.arguments_preview}</span>
                </div>
              ))}
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}
      {plan.status === "proposed" && (
        <div className="flex gap-2 pt-1">
          <Button
            size="sm"
            onClick={() => approveMutation.mutate()}
            disabled={approveMutation.isPending || denyMutation.isPending}
            data-testid={`button-approve-${plan.id}`}
          >
            <CheckCircle className="w-3.5 h-3.5 mr-1" />
            Approve
          </Button>
          <Button
            size="sm"
            variant="destructive"
            onClick={() => denyMutation.mutate()}
            disabled={approveMutation.isPending || denyMutation.isPending}
            data-testid={`button-deny-${plan.id}`}
          >
            <XCircle className="w-3.5 h-3.5 mr-1" />
            Deny
          </Button>
        </div>
      )}
    </div>
  );
}

function ToolRunCard({ run }: { run: AgentToolRun }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border rounded-lg p-2 bg-muted/20 text-xs" data-testid={`tool-run-${run.id}`}>
      <Collapsible open={open} onOpenChange={setOpen}>
        <CollapsibleTrigger className="flex items-center gap-2 w-full text-left">
          <Wrench className="w-3 h-3 text-muted-foreground shrink-0" />
          <span className="font-mono font-medium">{run.tool_name}</span>
          {run.is_error ? (
            <Badge variant="destructive" className="text-[9px]">error</Badge>
          ) : (
            <Badge variant="secondary" className="text-[9px] bg-emerald-500/10 text-emerald-700 dark:text-emerald-300">ok</Badge>
          )}
          {run.duration_ms != null && (
            <span className="text-muted-foreground ml-auto">{run.duration_ms}ms</span>
          )}
          <ChevronDown className={`w-3 h-3 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="mt-2 space-y-1.5">
            <div>
              <span className="text-muted-foreground">Args:</span>
              <pre className="mt-0.5 bg-muted/50 rounded p-1.5 whitespace-pre-wrap break-all text-[11px]">
                {JSON.stringify(run.arguments, null, 2)}
              </pre>
            </div>
            <div>
              <span className="text-muted-foreground">Result:</span>
              <pre className="mt-0.5 bg-muted/50 rounded p-1.5 whitespace-pre-wrap break-all text-[11px] max-h-40 overflow-y-auto">
                {run.result}
              </pre>
            </div>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}

function TurnMessage({ turn, plans, toolRuns, sessionId, onPlanAction }: {
  turn: AgentTurn;
  plans: AgentPlan[];
  toolRuns: AgentToolRun[];
  sessionId: string;
  onPlanAction: () => void;
}) {
  const isUser = turn.role === "user";
  const turnPlans = plans.filter(p => p.turn_id === turn.id);
  const turnToolRuns = toolRuns.filter(r => r.turn_id === turn.id);

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`} data-testid={`turn-${turn.id}`}>
      <div className={`max-w-[85%] space-y-2 ${isUser ? "items-end" : "items-start"}`}>
        <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
          <span className="font-medium">{isUser ? "You" : "Agent"}</span>
          <span>{ago(turn.created_at)}</span>
          <code className="font-mono">{turn.id.slice(0, 8)}</code>
        </div>
        <div
          className={`rounded-lg p-3 text-sm whitespace-pre-wrap break-words ${
            isUser
              ? "bg-primary text-primary-foreground"
              : "bg-muted/50 border"
          }`}
        >
          {turn.content || <span className="italic text-muted-foreground">(processing...)</span>}
        </div>

        {turnPlans.map(plan => (
          <PlanCard key={plan.id} plan={plan} sessionId={sessionId} onAction={onPlanAction} />
        ))}

        {turnToolRuns.length > 0 && (
          <div className="space-y-1.5">
            {turnToolRuns.map(run => (
              <ToolRunCard key={run.id} run={run} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ContextPanel({ sessionId }: { sessionId: string }) {
  const { data: decisions } = useQuery<AgentDecision[]>({
    queryKey: [`/api/agent/sessions/${sessionId}/decisions`],
    refetchInterval: 5_000,
    enabled: Boolean(sessionId),
  });

  const { data: toolRuns } = useQuery<AgentToolRun[]>({
    queryKey: [`/api/agent/sessions/${sessionId}/tool-runs`],
    refetchInterval: 5_000,
    enabled: Boolean(sessionId),
  });

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-xs font-medium text-muted-foreground mb-2">Recent Decisions</h3>
        {(!decisions || decisions.length === 0) ? (
          <p className="text-xs text-muted-foreground italic">No decisions yet</p>
        ) : (
          <div className="space-y-2">
            {decisions.slice(0, 10).map(d => (
              <div key={d.id} className="text-xs border rounded p-2 space-y-1">
                <div className="flex items-center gap-1.5">
                  {d.action === "allow" && <CheckCircle className="w-3 h-3 text-emerald-500" />}
                  {d.action === "deny" && <XCircle className="w-3 h-3 text-red-500" />}
                  {d.action === "escalate" && <AlertTriangle className="w-3 h-3 text-amber-500" />}
                  <span className="font-medium">{d.decision_type}</span>
                  <Badge variant="outline" className="text-[9px]">{d.action}</Badge>
                </div>
                <p className="text-muted-foreground">{d.explanation}</p>
                {d.rule_matched && (
                  <code className="text-[10px] text-muted-foreground">rule: {d.rule_matched}</code>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <Separator />

      <div>
        <h3 className="text-xs font-medium text-muted-foreground mb-2">Tool Execution Timeline</h3>
        {(!toolRuns || toolRuns.length === 0) ? (
          <p className="text-xs text-muted-foreground italic">No tool runs yet</p>
        ) : (
          <div className="space-y-1">
            {toolRuns.slice(0, 20).map(r => (
              <div key={r.id} className="flex items-center gap-2 text-[11px] font-mono">
                <span className={r.is_error ? "text-red-500" : "text-emerald-500"}>
                  {r.is_error ? "x" : "\u2713"}
                </span>
                <span className="truncate">{r.tool_name}</span>
                {r.duration_ms != null && (
                  <span className="text-muted-foreground ml-auto shrink-0">{r.duration_ms}ms</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function AgentPage() {
  const { toast } = useToast();
  const [selectedSession, setSelectedSession] = useState<string>("");
  const [message, setMessage] = useState("");
  const [showStartForm, setShowStartForm] = useState(false);
  const [startProvider, setStartProvider] = useState("anthropic");
  const [startModel, setStartModel] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  const { data: sessions, isLoading: sessionsLoading } = useQuery<Session[]>({
    queryKey: ["/api/sessions"],
    refetchInterval: 5_000,
  });

  const agentSessions = (sessions ?? []).filter(s => s.tool?.startsWith("agent"));

  const { data: agentState } = useQuery<AgentState>({
    queryKey: [`/api/agent/sessions/${selectedSession}/state`],
    refetchInterval: 2_000,
    enabled: Boolean(selectedSession),
  });

  const { data: turns } = useQuery<AgentTurn[]>({
    queryKey: [`/api/agent/sessions/${selectedSession}/turns`],
    refetchInterval: 3_000,
    enabled: Boolean(selectedSession),
  });

  const { data: plans } = useQuery<AgentPlan[]>({
    queryKey: [`/api/agent/sessions/${selectedSession}/plans`],
    refetchInterval: 3_000,
    enabled: Boolean(selectedSession),
  });

  const { data: toolRuns } = useQuery<AgentToolRun[]>({
    queryKey: [`/api/agent/sessions/${selectedSession}/tool-runs`],
    refetchInterval: 5_000,
    enabled: Boolean(selectedSession),
  });

  const sendMutation = useMutation({
    mutationFn: (text: string) =>
      apiRequest("POST", `/api/agent/sessions/${selectedSession}/message`, { text }),
    onSuccess: () => {
      setMessage("");
      queryClient.invalidateQueries({ queryKey: [`/api/agent/sessions/${selectedSession}/turns`] });
      queryClient.invalidateQueries({ queryKey: [`/api/agent/sessions/${selectedSession}/state`] });
    },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const startMutation = useMutation({
    mutationFn: async (opts: { provider: string; model: string }) => {
      const resp = await apiRequest("POST", "/api/agent/start", {
        provider: opts.provider,
        ...(opts.model ? { model: opts.model } : {}),
      });
      const ct = resp.headers.get("content-type") || "";
      if (!ct.includes("application/json")) {
        throw new Error("Server returned unexpected response. Restart the dashboard server.");
      }
      const data = await resp.json();
      if (!data.session_id) {
        throw new Error(data.error || "No session_id returned from server.");
      }
      return data as { ok: boolean; session_id: string };
    },
    onSuccess: (data) => {
      setShowStartForm(false);
      setStartModel("");
      setSelectedSession(data.session_id);
      queryClient.invalidateQueries({ queryKey: ["/api/sessions"] });
    },
    onError: (e: Error) =>
      toast({ title: "Failed to start agent", description: e.message, variant: "destructive" }),
  });

  const launchAgent = (provider: string, model: string) => {
    if (startMutation.isPending) return;
    startMutation.mutate({ provider, model });
  };

  const handleStartAgent = () => launchAgent(startProvider, startModel);

  const handleSend = () => {
    const text = message.trim();
    if (!text || !selectedSession) return;
    sendMutation.mutate(text);
  };

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: [`/api/agent/sessions/${selectedSession}/turns`] });
    queryClient.invalidateQueries({ queryKey: [`/api/agent/sessions/${selectedSession}/plans`] });
    queryClient.invalidateQueries({ queryKey: [`/api/agent/sessions/${selectedSession}/state`] });
  };

  // Auto-scroll when new turns arrive
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [turns?.length]);

  const copyTraceId = () => {
    if (agentState?.trace_id) {
      navigator.clipboard.writeText(agentState.trace_id).then(() =>
        toast({ title: "Trace ID copied" })
      );
    }
  };

  return (
    <div className="space-y-4" data-testid="agent-page">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-muted-foreground" />
            Expert Agent
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Governance-specialised operational agent with structured SoR persistence.
          </p>
        </div>
        {agentState && (
          <div className="flex items-center gap-2">
            {stateBadge(agentState.agent_state)}
            {agentState.trace_id && (
              <Button variant="ghost" size="sm" onClick={copyTraceId} className="h-6 text-[10px] font-mono gap-1">
                <Copy className="w-3 h-3" />
                {agentState.trace_id.slice(0, 8)}
              </Button>
            )}
          </div>
        )}
      </div>

      {/* Session selector */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium">Agent Session</CardTitle>
            {!showStartForm && agentSessions.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowStartForm(true)}
                className="h-7 text-xs gap-1"
                data-testid="button-start-agent-toggle"
              >
                <Plus className="w-3 h-3" />
                New Agent
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {showStartForm && (
            <div className="border rounded-lg p-3 space-y-3 bg-muted/30" data-testid="start-agent-form">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs">Provider</Label>
                  <Select value={startProvider} onValueChange={setStartProvider}>
                    <SelectTrigger data-testid="select-start-provider">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="anthropic">Anthropic</SelectItem>
                      <SelectItem value="openai">OpenAI</SelectItem>
                      <SelectItem value="google">Google</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Model (optional)</Label>
                  <Input
                    placeholder="e.g. claude-sonnet-4-5-20250514"
                    value={startModel}
                    onChange={e => setStartModel(e.target.value)}
                    className="text-xs font-mono"
                    data-testid="input-start-model"
                  />
                </div>
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={handleStartAgent}
                  disabled={startMutation.isPending}
                  data-testid="button-start-agent-confirm"
                >
                  {startMutation.isPending ? (
                    <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
                  ) : (
                    <Play className="w-3.5 h-3.5 mr-1" />
                  )}
                  {startMutation.isPending ? "Starting..." : "Launch Agent"}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setShowStartForm(false)}
                  disabled={startMutation.isPending}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}

          {sessionsLoading ? (
            <Skeleton className="h-9 w-full" />
          ) : startMutation.isPending ? (
            <div className="text-center py-8 space-y-3" data-testid="agent-starting">
              <Loader2 className="w-8 h-8 mx-auto text-muted-foreground animate-spin" />
              <p className="text-sm font-medium">Starting agent...</p>
            </div>
          ) : agentSessions.length === 0 && !showStartForm ? (
            <div className="text-center py-6 space-y-3">
              <Sparkles className="w-8 h-8 mx-auto text-muted-foreground/50" />
              <p className="text-sm text-muted-foreground">
                No agent sessions yet.
              </p>
              <Button
                variant="default"
                size="sm"
                onClick={() => setShowStartForm(true)}
                data-testid="button-start-agent-empty"
              >
                <Play className="w-3.5 h-3.5 mr-1" />
                Start Agent
              </Button>
            </div>
          ) : agentSessions.length > 0 ? (
            <Select value={selectedSession} onValueChange={setSelectedSession}>
              <SelectTrigger data-testid="select-agent-session">
                <SelectValue placeholder="Select an agent session..." />
              </SelectTrigger>
              <SelectContent>
                {agentSessions.map(s => (
                  <SelectItem key={s.id} value={s.id}>
                    <span className="font-mono text-xs">{s.id.slice(0, 8)}</span>
                    <span className="ml-2 text-muted-foreground">{s.status}</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : null}
        </CardContent>
      </Card>

      {selectedSession && (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4">
          {/* Main conversation panel */}
          <Card className="flex flex-col" style={{ minHeight: "60vh" }}>
            <CardHeader className="pb-2 shrink-0">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium">Conversation</CardTitle>
                <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                  {agentState && (
                    <>
                      <span>{agentState.total_turns} turn{agentState.total_turns !== 1 ? "s" : ""}</span>
                      {agentState.latest_plan_status && (
                        <Badge variant="outline" className="text-[9px]">
                          plan: {agentState.latest_plan_status}
                        </Badge>
                      )}
                    </>
                  )}
                </div>
              </div>
            </CardHeader>

            <ScrollArea className="flex-1 px-4" ref={scrollRef}>
              <div className="space-y-4 py-4" data-testid="conversation-feed">
                {(!turns || turns.length === 0) ? (
                  <div className="text-center py-12 text-sm text-muted-foreground">
                    Send a message to start the conversation.
                  </div>
                ) : (
                  turns.map(turn => (
                    <TurnMessage
                      key={turn.id}
                      turn={turn}
                      plans={plans ?? []}
                      toolRuns={toolRuns ?? []}
                      sessionId={selectedSession}
                      onPlanAction={invalidateAll}
                    />
                  ))
                )}
              </div>
            </ScrollArea>

            <div className="p-4 border-t shrink-0">
              <div className="flex gap-2">
                <Input
                  placeholder="Send a message to the agent..."
                  value={message}
                  onChange={e => setMessage(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && !e.shiftKey && handleSend()}
                  disabled={sendMutation.isPending}
                  data-testid="input-agent-message"
                  className="font-mono text-sm"
                />
                <Button
                  onClick={handleSend}
                  disabled={!message.trim() || sendMutation.isPending}
                  data-testid="button-agent-send"
                >
                  <Send className="w-3.5 h-3.5 mr-1" />
                  {sendMutation.isPending ? "Sending..." : "Send"}
                </Button>
              </div>
            </div>
          </Card>

          {/* Context panel */}
          <Card className="hidden lg:block" style={{ minHeight: "60vh" }}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Context</CardTitle>
            </CardHeader>
            <CardContent>
              <ContextPanel sessionId={selectedSession} />
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
