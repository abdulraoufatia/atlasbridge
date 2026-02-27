import { useQuery, useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { apiRequest, queryClient } from "@/lib/queryClient";
import type { Session } from "@shared/schema";
import { Bot, Clock, Send } from "lucide-react";

interface PendingPrompt {
  id: string;
  excerpt: string;
  prompt_type: string;
  confidence: string;
  created_at: string;
  session_id: string;
}

const SESSIONS_QUERY_KEY = ["/api/sessions"];

function ago(d: string): string {
  const diff = Date.now() - new Date(d).getTime();
  if (diff < 60000) return "just now";
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  return `${Math.floor(diff / 3600000)}h ago`;
}

export default function ChatPage() {
  const { toast } = useToast();
  const [selectedSession, setSelectedSession] = useState<string>("");
  const [replyValues, setReplyValues] = useState<Record<string, string>>({});

  const { data: sessions, isLoading: sessionsLoading } = useQuery<Session[]>({
    queryKey: SESSIONS_QUERY_KEY,
    refetchInterval: 5_000,
  });

  const activeSessions = (sessions ?? []).filter((s) => s.status === "running");

  const promptsQueryKey = ["/api/chat/prompts", selectedSession];
  const { data: prompts, isLoading: promptsLoading } = useQuery<PendingPrompt[]>({
    queryKey: promptsQueryKey,
    queryFn: () =>
      apiRequest("GET", `/api/chat/prompts?session_id=${encodeURIComponent(selectedSession)}`)
        .then((r) => r.json()),
    enabled: Boolean(selectedSession),
    refetchInterval: 3_000,
  });

  const replyMutation = useMutation({
    mutationFn: (vars: { prompt_id: string; value: string }) =>
      apiRequest("POST", "/api/chat/reply", {
        session_id: selectedSession,
        prompt_id: vars.prompt_id,
        value: vars.value,
      }),
    onSuccess: (_data, vars) => {
      toast({ title: "Reply sent" });
      setReplyValues((p) => { const n = { ...p }; delete n[vars.prompt_id]; return n; });
      queryClient.invalidateQueries({ queryKey: promptsQueryKey });
    },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const handleReply = (promptId: string) => {
    const value = replyValues[promptId]?.trim();
    if (!value) return;
    replyMutation.mutate({ prompt_id: promptId, value });
  };

  const confidenceBadgeCls = (conf: string) => {
    switch (conf.toLowerCase()) {
      case "high": return "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
      case "medium": return "bg-amber-500/10 text-amber-700 dark:text-amber-300";
      default: return "bg-red-500/10 text-red-700 dark:text-red-300";
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight flex items-center gap-2">
          <Bot className="w-5 h-5 text-muted-foreground" />
          Chat
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Reply to pending prompts in an active agent session.
        </p>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">Active session</CardTitle>
        </CardHeader>
        <CardContent>
          {sessionsLoading ? (
            <Skeleton className="h-9 w-full" />
          ) : activeSessions.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No active sessions. Start one with{" "}
              <code className="text-xs bg-muted px-1.5 py-0.5 rounded">atlasbridge run claude</code>
              {" "}or from the Sessions page.
            </p>
          ) : (
            <Select value={selectedSession} onValueChange={setSelectedSession}>
              <SelectTrigger data-testid="select-chat-session">
                <SelectValue placeholder="Select a session…" />
              </SelectTrigger>
              <SelectContent>
                {activeSessions.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    <span className="font-mono text-xs">{s.id.slice(0, 8)}</span>
                    <span className="ml-2 text-muted-foreground">{s.tool}</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </CardContent>
      </Card>

      {selectedSession && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Pending prompts</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {promptsLoading ? (
              <div className="p-4 space-y-3">
                <Skeleton className="h-20 w-full" />
                <Skeleton className="h-20 w-full" />
              </div>
            ) : !prompts || prompts.length === 0 ? (
              <div
                className="p-6 text-center text-sm text-muted-foreground"
                data-testid="text-no-prompts"
              >
                No pending prompts. The agent will appear here when it needs a decision.
              </div>
            ) : (
              <div className="divide-y" data-testid="prompt-list">
                {prompts.map((prompt) => (
                  <div
                    key={prompt.id}
                    className="p-4 space-y-3"
                    data-testid={`prompt-row-${prompt.id}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Badge variant="secondary" className="text-[10px] font-mono">
                          {prompt.prompt_type}
                        </Badge>
                        <Badge
                          variant="secondary"
                          className={`text-[10px] ${confidenceBadgeCls(prompt.confidence)}`}
                        >
                          {prompt.confidence}
                        </Badge>
                        <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                          <Clock className="w-3 h-3" />
                          {ago(prompt.created_at)}
                        </span>
                      </div>
                      <code className="text-[10px] text-muted-foreground font-mono shrink-0">
                        {prompt.id.slice(0, 8)}
                      </code>
                    </div>

                    <pre className="text-sm font-mono bg-muted/50 rounded p-3 whitespace-pre-wrap break-words leading-relaxed">
                      {prompt.excerpt || "(no excerpt)"}
                    </pre>

                    <div className="flex gap-2">
                      <Input
                        placeholder="Type your reply…"
                        value={replyValues[prompt.id] ?? ""}
                        onChange={(e) =>
                          setReplyValues((p) => ({ ...p, [prompt.id]: e.target.value }))
                        }
                        onKeyDown={(e) => e.key === "Enter" && handleReply(prompt.id)}
                        data-testid={`input-reply-${prompt.id}`}
                        className="font-mono text-sm"
                      />
                      <Button
                        size="sm"
                        onClick={() => handleReply(prompt.id)}
                        disabled={!replyValues[prompt.id]?.trim() || replyMutation.isPending}
                        data-testid={`button-reply-${prompt.id}`}
                      >
                        <Send className="w-3.5 h-3.5 mr-1" />
                        {replyMutation.isPending ? "Sending…" : "Send"}
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
