import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { apiRequest } from "@/lib/queryClient";
import { FolderCheck, ShieldCheck, ShieldOff, Plus } from "lucide-react";

interface WorkspaceRecord {
  id: string;
  path: string;
  path_hash: string;
  trusted: number;
  actor: string | null;
  channel: string | null;
  session_id: string | null;
  granted_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

const QUERY_KEY = ["/api/workspaces"];

export default function WorkspacesPage() {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const { data: workspaces, isLoading } = useQuery<WorkspaceRecord[]>({
    queryKey: QUERY_KEY,
    refetchInterval: 10_000,
  });

  const [newPath, setNewPath] = useState("");
  const [showAdd, setShowAdd] = useState(false);

  const trustMutation = useMutation({
    mutationFn: (path: string) => apiRequest("POST", "/api/workspaces/trust", { path }),
    onSuccess: () => {
      toast({ title: "Trust granted", description: "Workspace marked as trusted." });
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
      setNewPath("");
      setShowAdd(false);
    },
    onError: (e: Error) =>
      toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const revokeMutation = useMutation({
    mutationFn: (path: string) => apiRequest("DELETE", "/api/workspaces/trust", { path }),
    onSuccess: () => {
      toast({ title: "Trust revoked", description: "Workspace trust removed." });
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
    onError: (e: Error) =>
      toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const handleTrust = () => {
    const p = newPath.trim();
    if (!p) return;
    trustMutation.mutate(p);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Workspace Trust</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage runtime consent for workspace directories. A trusted workspace is
            automatically approved when the agent requests access — no channel prompt needed.
          </p>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => setShowAdd(!showAdd)}
          data-testid="button-add-workspace"
        >
          <Plus className="w-4 h-4 mr-1.5" />
          Grant Trust
        </Button>
      </div>

      {showAdd && (
        <Card data-testid="card-add-workspace">
          <CardHeader>
            <CardTitle className="text-base">Grant workspace trust</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-3">
              Enter the absolute path of the workspace directory to trust. Future sessions
              using this path will auto-approve without sending a channel prompt.
            </p>
            <div className="flex gap-2">
              <Input
                placeholder="/path/to/workspace"
                value={newPath}
                onChange={e => setNewPath(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleTrust()}
                data-testid="input-workspace-path"
                className="font-mono text-sm"
              />
              <Button
                onClick={handleTrust}
                disabled={!newPath.trim() || trustMutation.isPending}
                data-testid="button-grant-trust"
              >
                {trustMutation.isPending ? "Saving…" : "Grant"}
              </Button>
              <Button variant="ghost" onClick={() => { setShowAdd(false); setNewPath(""); }}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <FolderCheck className="w-4 h-4 text-muted-foreground" />
            Recorded workspaces
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-4 space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : !workspaces || workspaces.length === 0 ? (
            <div className="p-6 text-center text-sm text-muted-foreground" data-testid="text-no-workspaces">
              No workspaces recorded yet. Grant trust to a directory above or start a session
              that requests workspace access.
            </div>
          ) : (
            <div className="divide-y" data-testid="workspace-list">
              {workspaces.map(ws => {
                const isTrusted = Boolean(ws.trusted);
                return (
                  <div
                    key={ws.id}
                    className="flex items-center justify-between gap-3 px-4 py-3"
                    data-testid={`workspace-row-${ws.id}`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      {isTrusted ? (
                        <ShieldCheck className="w-4 h-4 text-emerald-500 shrink-0" />
                      ) : (
                        <ShieldOff className="w-4 h-4 text-muted-foreground shrink-0" />
                      )}
                      <div className="min-w-0">
                        <p className="text-sm font-mono truncate" title={ws.path}>
                          {ws.path}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {ws.actor ? `via ${ws.actor}` : ""}
                          {ws.granted_at
                            ? ` · ${new Date(ws.granted_at).toLocaleString()}`
                            : ""}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Badge
                        variant={isTrusted ? "default" : "secondary"}
                        className={isTrusted ? "bg-emerald-600 text-white" : ""}
                        data-testid={`badge-trust-${ws.id}`}
                      >
                        {isTrusted ? "Trusted" : "Not trusted"}
                      </Badge>
                      {isTrusted ? (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="text-destructive hover:text-destructive"
                          onClick={() => revokeMutation.mutate(ws.path)}
                          disabled={revokeMutation.isPending}
                          data-testid={`button-revoke-${ws.id}`}
                        >
                          Revoke
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => trustMutation.mutate(ws.path)}
                          disabled={trustMutation.isPending}
                          data-testid={`button-trust-${ws.id}`}
                        >
                          Trust
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
