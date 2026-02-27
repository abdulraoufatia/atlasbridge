import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useLocation } from "wouter";
import type { Session } from "@shared/schema";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import { apiRequest } from "@/lib/queryClient";
import { riskBg, statusColor, ciColor, formatTimestamp, timeAgo } from "@/lib/utils";
import { Search, ExternalLink, Play, Square, Pause } from "lucide-react";

const ACTIVE_STATUSES = new Set(["starting", "running", "awaiting_reply"]);
const PAUSABLE_STATUSES = new Set(["running", "awaiting_reply"]);

function StartSessionDialog({
  open,
  onOpenChange,
  onSessionStarted,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onSessionStarted?: () => void;
}) {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [adapter, setAdapter] = useState("claude");
  const [mode, setMode] = useState("off");
  const [cwd, setCwd] = useState("");
  const [label, setLabel] = useState("");
  const [customCommand, setCustomCommand] = useState("");

  const startMutation = useMutation({
    mutationFn: () =>
      apiRequest("POST", "/api/sessions/start", {
        adapter,
        mode,
        cwd: cwd || undefined,
        label: label || undefined,
        ...(adapter === "custom" ? { customCommand } : {}),
      }),
    onSuccess: () => {
      toast({ title: "Session started", description: `${adapter === "custom" ? customCommand.split(" ")[0] : adapter} (${mode}) session launched.` });
      queryClient.refetchQueries({ queryKey: ["/api/sessions"] });
      // The background process needs a moment to write to the DB — refetch again shortly
      setTimeout(() => queryClient.refetchQueries({ queryKey: ["/api/sessions"] }), 1500);
      setTimeout(() => queryClient.refetchQueries({ queryKey: ["/api/sessions"] }), 3000);
      onOpenChange(false);
      onSessionStarted?.();
      setAdapter("claude");
      setMode("off");
      setCwd("");
      setLabel("");
      setCustomCommand("");
    },
    onError: (e: Error) =>
      toast({ title: "Failed to start session", description: e.message, variant: "destructive" }),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" data-testid="dialog-start-session">
        <DialogHeader>
          <DialogTitle>Start Session</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="adapter-select" className="text-xs text-muted-foreground">Adapter</Label>
            <Select value={adapter} onValueChange={v => { setAdapter(v); setCustomCommand(""); }}>
              <SelectTrigger id="adapter-select" data-testid="select-adapter">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="claude">Claude Code</SelectItem>
                <SelectItem value="claude-code">Claude Code (alias)</SelectItem>
                <SelectItem value="openai">OpenAI CLI</SelectItem>
                <SelectItem value="gemini">Gemini CLI</SelectItem>
                <SelectItem value="custom">Custom (any tool)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {adapter === "custom" && (
            <div className="space-y-1.5">
              <Label htmlFor="custom-command-input" className="text-xs text-muted-foreground">
                Command
              </Label>
              <Input
                id="custom-command-input"
                placeholder="e.g. cursor, aider --model gpt-4o"
                value={customCommand}
                onChange={e => setCustomCommand(e.target.value)}
                data-testid="input-custom-command"
                className="font-mono text-sm"
              />
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="mode-select" className="text-xs text-muted-foreground">Autonomy Mode</Label>
            <Select value={mode} onValueChange={setMode}>
              <SelectTrigger id="mode-select" data-testid="select-mode">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="off">Off — all prompts escalated</SelectItem>
                <SelectItem value="assist">Assist — policy handles permitted</SelectItem>
                <SelectItem value="full">Full — policy auto-executes</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="cwd-input" className="text-xs text-muted-foreground">
              Workspace path <span className="text-muted-foreground/60">(optional)</span>
            </Label>
            <Input
              id="cwd-input"
              placeholder="/path/to/project"
              value={cwd}
              onChange={e => setCwd(e.target.value)}
              data-testid="input-cwd"
              className="font-mono text-sm"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="label-input" className="text-xs text-muted-foreground">
              Label <span className="text-muted-foreground/60">(optional)</span>
            </Label>
            <Input
              id="label-input"
              placeholder="e.g. feature-branch-work"
              value={label}
              onChange={e => setLabel(e.target.value)}
              data-testid="input-label"
              className="text-sm"
            />
          </div>
        </div>
        <DialogFooter className="gap-2">
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={startMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            onClick={() => startMutation.mutate()}
            disabled={startMutation.isPending || (adapter === "custom" && !customCommand.trim())}
            data-testid="button-confirm-start"
          >
            {startMutation.isPending ? "Starting…" : "Start Session"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function SessionsPage() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [, navigate] = useLocation();

  const { data: sessions, isLoading } = useQuery<Session[]>({
    queryKey: ["/api/sessions"],
    refetchInterval: 2_000,
  });

  const [search, setSearch] = useState("");
  const [riskFilter, setRiskFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [ciFilter, setCiFilter] = useState<string>("all");
  const [startDialogOpen, setStartDialogOpen] = useState(false);
  const [stoppingId, setStoppingId] = useState<string | null>(null);
  const [pausingId, setPausingId] = useState<string | null>(null);

  const navigateToChat = () => {
    // Wait for the session to appear in the DB, then navigate to chat
    const pollForSession = (attempts: number) => {
      if (attempts <= 0) {
        navigate("/chat");
        return;
      }
      apiRequest("GET", "/api/sessions").then((r) => r.json()).then((list: Session[]) => {
        const newest = list
          .filter((s: Session) => s.status === "running")
          .sort((a: Session, b: Session) => new Date(b.startTime).getTime() - new Date(a.startTime).getTime())[0];
        if (newest) {
          navigate(`/chat?sessionId=${newest.id}`);
        } else {
          setTimeout(() => pollForSession(attempts - 1), 1000);
        }
      }).catch(() => {
        navigate("/chat");
      });
    };
    // Give the daemon ~2s to write the session to the DB
    setTimeout(() => pollForSession(3), 2000);
  };

  const stopMutation = useMutation({
    mutationFn: (sessionId: string) =>
      apiRequest("POST", `/api/sessions/${sessionId}/stop`, {}),
    onSuccess: (_data, sessionId) => {
      toast({ title: "Session stopped", description: `Session ${sessionId.slice(0, 8)} received stop signal.` });
      queryClient.refetchQueries({ queryKey: ["/api/sessions"] });
      setStoppingId(null);
    },
    onError: (e: Error) => {
      toast({ title: "Stop failed", description: e.message, variant: "destructive" });
      setStoppingId(null);
    },
  });

  const pauseMutation = useMutation({
    mutationFn: (sessionId: string) =>
      apiRequest("POST", `/api/sessions/${sessionId}/pause`, {}),
    onSuccess: (_data, sessionId) => {
      toast({ title: "Session paused", description: `Session ${sessionId.slice(0, 8)} paused.` });
      queryClient.refetchQueries({ queryKey: ["/api/sessions"] });
      setPausingId(null);
    },
    onError: (e: Error) => {
      toast({ title: "Pause failed", description: e.message, variant: "destructive" });
      setPausingId(null);
    },
  });

  const resumeMutation = useMutation({
    mutationFn: (sessionId: string) =>
      apiRequest("POST", `/api/sessions/${sessionId}/resume`, {}),
    onSuccess: (_data, sessionId) => {
      toast({ title: "Session resumed", description: `Session ${sessionId.slice(0, 8)} resumed.` });
      queryClient.refetchQueries({ queryKey: ["/api/sessions"] });
    },
    onError: (e: Error) => {
      toast({ title: "Resume failed", description: e.message, variant: "destructive" });
    },
  });

  const handleStop = (sessionId: string) => {
    setStoppingId(sessionId);
    stopMutation.mutate(sessionId);
  };

  const handlePause = (sessionId: string) => {
    setPausingId(sessionId);
    pauseMutation.mutate(sessionId);
  };

  const filtered = sessions?.filter(s => {
    if (search && !s.id.toLowerCase().includes(search.toLowerCase()) && !s.tool.toLowerCase().includes(search.toLowerCase())) return false;
    if (riskFilter !== "all" && s.riskLevel !== riskFilter) return false;
    if (statusFilter !== "all" && s.status !== statusFilter) return false;
    if (ciFilter !== "all" && s.ciSnapshot !== ciFilter) return false;
    return true;
  }) || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Sessions</h1>
          <p className="text-sm text-muted-foreground mt-1">Active and historical agent sessions</p>
        </div>
        <Button
          size="sm"
          onClick={() => setStartDialogOpen(true)}
          data-testid="button-start-session"
        >
          <Play className="w-3.5 h-3.5 mr-1.5" />
          Start Session
        </Button>
      </div>

      <StartSessionDialog open={startDialogOpen} onOpenChange={setStartDialogOpen} onSessionStarted={navigateToChat} />

      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Search by session ID or tool..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="pl-9"
                data-testid="input-session-search"
              />
            </div>
            <div className="flex gap-2 flex-wrap">
              <Select value={riskFilter} onValueChange={setRiskFilter}>
                <SelectTrigger className="w-[130px]" data-testid="select-risk-filter">
                  <SelectValue placeholder="Risk Level" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Risks</SelectItem>
                  <SelectItem value="low">Low</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="high">High</SelectItem>
                  <SelectItem value="critical">Critical</SelectItem>
                </SelectContent>
              </Select>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-[130px]" data-testid="select-status-filter">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="starting">Starting</SelectItem>
                  <SelectItem value="running">Running</SelectItem>
                  <SelectItem value="awaiting_reply">Awaiting Reply</SelectItem>
                  <SelectItem value="completed">Completed</SelectItem>
                  <SelectItem value="crashed">Crashed</SelectItem>
                  <SelectItem value="canceled">Canceled</SelectItem>
                </SelectContent>
              </Select>
              <Select value={ciFilter} onValueChange={setCiFilter}>
                <SelectTrigger className="w-[120px]" data-testid="select-ci-filter">
                  <SelectValue placeholder="CI" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All CI</SelectItem>
                  <SelectItem value="pass">Pass</SelectItem>
                  <SelectItem value="fail">Fail</SelectItem>
                  <SelectItem value="unknown">Unknown</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {isLoading ? (
        <Card>
          <CardContent className="p-4 space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs">Session ID</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs">Tool</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs hidden lg:table-cell">Started</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs hidden md:table-cell">Last Activity</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs">Status</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs">Risk</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs hidden sm:table-cell">Esc.</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs hidden sm:table-cell">CI</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs"></th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="px-4 py-8 text-center text-muted-foreground">
                      No sessions match your filters
                    </td>
                  </tr>
                ) : (
                  filtered.map(session => (
                    <tr key={session.id} className="border-b last:border-0" data-testid={`row-session-${session.id}`}>
                      <td className="px-4 py-3">
                        <span className="font-mono text-xs">{session.id}</span>
                      </td>
                      <td className="px-4 py-3 font-medium">{session.tool}</td>
                      <td className="px-4 py-3 text-muted-foreground text-xs hidden lg:table-cell">
                        {formatTimestamp(session.startTime)}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground text-xs hidden md:table-cell">
                        {timeAgo(session.lastActivity)}
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant="secondary" className={`text-[10px] ${statusColor(session.status)}`}>
                          {session.status}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant="secondary" className={`text-[10px] capitalize ${riskBg(session.riskLevel)}`}>
                          {session.riskLevel}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-center hidden sm:table-cell">
                        {session.escalationsCount > 0 ? (
                          <span className="text-orange-600 dark:text-orange-400 font-medium text-xs">{session.escalationsCount}</span>
                        ) : (
                          <span className="text-muted-foreground text-xs">0</span>
                        )}
                      </td>
                      <td className="px-4 py-3 hidden sm:table-cell">
                        <Badge variant="secondary" className={`text-[10px] ${ciColor(session.ciSnapshot)}`}>
                          {session.ciSnapshot}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <Link href={`/sessions/${session.id}`}>
                            <button className="text-primary text-xs flex items-center gap-1" data-testid={`link-session-${session.id}`}>
                              View <ExternalLink className="w-3 h-3" />
                            </button>
                          </Link>
                          {PAUSABLE_STATUSES.has(session.status) && (
                            <button
                              className="text-amber-600 dark:text-amber-400 text-xs flex items-center gap-1 disabled:opacity-50"
                              onClick={() => handlePause(session.id)}
                              disabled={pausingId === session.id}
                              data-testid={`button-pause-${session.id}`}
                              title="Pause session"
                            >
                              <Pause className="w-3 h-3" />
                              {pausingId === session.id ? "…" : "Pause"}
                            </button>
                          )}
                          {session.status === "paused" && (
                            <button
                              className="text-green-600 dark:text-green-400 text-xs flex items-center gap-1 disabled:opacity-50"
                              onClick={() => resumeMutation.mutate(session.id)}
                              disabled={resumeMutation.isPending}
                              data-testid={`button-resume-${session.id}`}
                              title="Resume session"
                            >
                              <Play className="w-3 h-3" />
                              Resume
                            </button>
                          )}
                          {(ACTIVE_STATUSES.has(session.status) || session.status === "paused") && (
                            <button
                              className="text-destructive text-xs flex items-center gap-1 disabled:opacity-50"
                              onClick={() => handleStop(session.id)}
                              disabled={stoppingId === session.id}
                              data-testid={`button-stop-${session.id}`}
                              title="Stop session"
                            >
                              <Square className="w-3 h-3" />
                              {stoppingId === session.id ? "…" : "Stop"}
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
