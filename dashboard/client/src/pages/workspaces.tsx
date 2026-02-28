import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { useToast } from "@/hooks/use-toast";
import { apiRequest } from "@/lib/queryClient";
import {
  FolderCheck, ShieldCheck, ShieldOff, Plus, ScanSearch,
  Pencil, Clock, AlertTriangle, ChevronRight, Loader2,
} from "lucide-react";

interface WorkspaceRecord {
  id: string;
  path: string;
  path_hash: string;
  trusted: number;
  trust_state?: string;
  trust_expired?: boolean;
  trust_expires_at?: string | null;
  actor: string | null;
  channel: string | null;
  session_id: string | null;
  granted_at: string | null;
  revoked_at: string | null;
  created_at: string;
  profile_name?: string | null;
  autonomy_default?: string | null;
  model_tier?: string | null;
  tool_allowlist_profile?: string | null;
  posture_notes?: string | null;
}

interface ScanResult {
  risk_tags: string[];
  suggested_profile: string | null;
  inputs_hash: string;
  file_count?: number;
  ruleset_version?: string;
  scanner_version?: string;
}

const TTL_OPTIONS = [
  { value: "", label: "No expiry" },
  { value: "1h", label: "1 hour" },
  { value: "8h", label: "8 hours" },
  { value: "1d", label: "1 day" },
  { value: "7d", label: "7 days" },
  { value: "30d", label: "30 days" },
];

const QUERY_KEY = ["/api/workspaces"];

function TrustBadge({ ws }: { ws: WorkspaceRecord }) {
  const isTrusted = Boolean(ws.trusted) || ws.trust_state === "trusted";
  const isExpired = Boolean(ws.trust_expired);

  if (isTrusted && !isExpired) {
    return (
      <Badge className="bg-emerald-600 text-white">
        <ShieldCheck className="w-3 h-3 mr-1" />
        Trusted
      </Badge>
    );
  }
  if (isExpired) {
    return (
      <Badge variant="outline" className="text-amber-600 border-amber-500/50">
        <Clock className="w-3 h-3 mr-1" />
        Expired
      </Badge>
    );
  }
  return (
    <Badge variant="secondary">
      <ShieldOff className="w-3 h-3 mr-1" />
      Not trusted
    </Badge>
  );
}

function RiskTag({ tag }: { tag: string }) {
  const colors: Record<string, string> = {
    iac: "bg-amber-500/15 text-amber-600 border-amber-500/30",
    secrets_present: "bg-red-500/15 text-red-600 border-red-500/30",  // pragma: allowlist secret
    deployment: "bg-cyan-500/15 text-cyan-600 border-cyan-500/30",
    unknown: "bg-muted text-muted-foreground",
  };
  return (
    <Badge variant="outline" className={colors[tag] || colors.unknown}>
      {tag === "secrets_present" ? "secrets" : tag}
    </Badge>
  );
}

export default function WorkspacesPage() {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const { data: workspaces, isLoading } = useQuery<WorkspaceRecord[]>({
    queryKey: QUERY_KEY,
    refetchInterval: 10_000,
  });

  const [showAdd, setShowAdd] = useState(false);
  const [newPath, setNewPath] = useState("");
  const [newTtl, setNewTtl] = useState("");

  // Detail / posture / scan state
  const [selectedWs, setSelectedWs] = useState<WorkspaceRecord | null>(null);
  const [showPosture, setShowPosture] = useState(false);
  const [postureProfile, setPostureProfile] = useState("");
  const [postureAutonomy, setPostureAutonomy] = useState("");
  const [postureModelTier, setPostureModelTier] = useState("");
  const [postureToolProfile, setPostureToolProfile] = useState("");
  const [postureNotes, setPostureNotes] = useState("");
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);

  // --- Mutations ---

  const trustMutation = useMutation({
    mutationFn: (args: { path: string; ttl?: string }) =>
      apiRequest("POST", "/api/workspaces/trust", { path: args.path, ttl: args.ttl || undefined }),
    onSuccess: () => {
      toast({ title: "Trust granted" });
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
      setNewPath("");
      setNewTtl("");
      setShowAdd(false);
    },
    onError: (e: Error) =>
      toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const revokeMutation = useMutation({
    mutationFn: (path: string) => apiRequest("DELETE", "/api/workspaces/trust", { path }),
    onSuccess: () => {
      toast({ title: "Trust revoked" });
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
      setSelectedWs(null);
    },
    onError: (e: Error) =>
      toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const postureMutation = useMutation({
    mutationFn: (args: Record<string, string>) =>
      apiRequest("POST", "/api/workspaces/posture", args),
    onSuccess: () => {
      toast({ title: "Posture updated" });
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
      setShowPosture(false);
    },
    onError: (e: Error) =>
      toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const scanMutation = useMutation({
    mutationFn: (path: string) =>
      apiRequest("POST", "/api/workspaces/scan", { path }).then(r => r.json()),
    onSuccess: (data: ScanResult) => {
      setScanResult(data);
      toast({
        title: "Scan complete",
        description: `${data.risk_tags?.length || 0} risk tag(s) found`,
      });
    },
    onError: (e: Error) =>
      toast({ title: "Scan failed", description: e.message, variant: "destructive" }),
  });

  // --- Handlers ---

  const handleTrust = () => {
    const p = newPath.trim();
    if (!p) return;
    trustMutation.mutate({ path: p, ttl: newTtl || undefined });
  };

  const openDetail = (ws: WorkspaceRecord) => {
    setSelectedWs(ws);
    setScanResult(null);
    setShowPosture(false);
    setPostureProfile(ws.profile_name || "");
    setPostureAutonomy(ws.autonomy_default || "");
    setPostureModelTier(ws.model_tier || "");
    setPostureToolProfile(ws.tool_allowlist_profile || "");
    setPostureNotes(ws.posture_notes || "");
  };

  const handlePostureSave = () => {
    if (!selectedWs) return;
    const body: Record<string, string> = { path: selectedWs.path };
    if (postureProfile) body.profile = postureProfile;
    if (postureAutonomy) body.autonomy = postureAutonomy;
    if (postureModelTier) body.model_tier = postureModelTier;
    if (postureToolProfile) body.tool_profile = postureToolProfile;
    if (postureNotes) body.notes = postureNotes;
    if (Object.keys(body).length <= 1) {
      toast({ title: "No changes", description: "Set at least one posture field.", variant: "destructive" });
      return;
    }
    postureMutation.mutate(body);
  };

  const handleApplyProfile = (profile: string) => {
    if (!selectedWs) return;
    postureMutation.mutate({ path: selectedWs.path, profile });
  };

  const isTrusted = (ws: WorkspaceRecord) =>
    Boolean(ws.trusted) || ws.trust_state === "trusted";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Workspace Governance</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage trust, posture bindings, and advisory scans for workspace directories.
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

      {/* Trust form */}
      {showAdd && (
        <Card data-testid="card-add-workspace">
          <CardHeader>
            <CardTitle className="text-base">Grant workspace trust</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-3">
              Enter the absolute path of the workspace directory. Optionally set a TTL
              so trust expires automatically.
            </p>
            <div className="flex gap-2 flex-wrap">
              <Input
                placeholder="/path/to/workspace"
                value={newPath}
                onChange={e => setNewPath(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleTrust()}
                data-testid="input-workspace-path"
                className="font-mono text-sm flex-1 min-w-[200px]"
              />
              <Select value={newTtl} onValueChange={setNewTtl}>
                <SelectTrigger className="w-[140px]" data-testid="select-ttl">
                  <SelectValue placeholder="No expiry" />
                </SelectTrigger>
                <SelectContent>
                  {TTL_OPTIONS.map(opt => (
                    <SelectItem key={opt.value} value={opt.value || "none"}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                onClick={handleTrust}
                disabled={!newPath.trim() || trustMutation.isPending}
                data-testid="button-grant-trust"
              >
                {trustMutation.isPending ? "Saving..." : "Grant"}
              </Button>
              <Button variant="ghost" onClick={() => { setShowAdd(false); setNewPath(""); setNewTtl(""); }}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Workspace list */}
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
              {workspaces.map(ws => (
                <button
                  key={ws.id}
                  className="flex items-center justify-between gap-3 px-4 py-3 w-full text-left hover:bg-muted/50 transition-colors"
                  onClick={() => openDetail(ws)}
                  data-testid={`workspace-row-${ws.id}`}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    {isTrusted(ws) ? (
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
                        {ws.profile_name ? ` · profile: ${ws.profile_name}` : ""}
                        {ws.autonomy_default ? ` · ${ws.autonomy_default}` : ""}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <TrustBadge ws={ws} />
                    <ChevronRight className="w-4 h-4 text-muted-foreground" />
                  </div>
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Workspace detail dialog */}
      <Dialog open={!!selectedWs} onOpenChange={open => { if (!open) setSelectedWs(null); }}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          {selectedWs && (
            <>
              <DialogHeader>
                <DialogTitle className="font-mono text-sm break-all">
                  {selectedWs.path}
                </DialogTitle>
              </DialogHeader>

              {/* Trust status + actions */}
              <div className="flex items-center justify-between gap-3">
                <TrustBadge ws={selectedWs} />
                <div className="flex gap-2">
                  {isTrusted(selectedWs) ? (
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => revokeMutation.mutate(selectedWs.path)}
                      disabled={revokeMutation.isPending}
                    >
                      {revokeMutation.isPending ? "Revoking..." : "Revoke Trust"}
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      onClick={() => trustMutation.mutate({ path: selectedWs.path })}
                      disabled={trustMutation.isPending}
                    >
                      {trustMutation.isPending ? "Granting..." : "Grant Trust"}
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setShowPosture(!showPosture)}
                  >
                    <Pencil className="w-3.5 h-3.5 mr-1.5" />
                    Edit Posture
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => scanMutation.mutate(selectedWs.path)}
                    disabled={scanMutation.isPending}
                  >
                    {scanMutation.isPending ? (
                      <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                    ) : (
                      <ScanSearch className="w-3.5 h-3.5 mr-1.5" />
                    )}
                    {scanMutation.isPending ? "Scanning..." : "Run Scan"}
                  </Button>
                </div>
              </div>

              {/* Details table */}
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm mt-2">
                <div>
                  <span className="text-muted-foreground">Actor</span>
                  <p>{selectedWs.actor || "--"}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Channel</span>
                  <p>{selectedWs.channel || "--"}</p>
                </div>
                {selectedWs.granted_at && (
                  <div>
                    <span className="text-muted-foreground">Granted</span>
                    <p>{new Date(selectedWs.granted_at).toLocaleString()}</p>
                  </div>
                )}
                {selectedWs.trust_expires_at && (
                  <div>
                    <span className="text-muted-foreground">Expires</span>
                    <p>{new Date(selectedWs.trust_expires_at).toLocaleString()}</p>
                  </div>
                )}
                {selectedWs.revoked_at && (
                  <div>
                    <span className="text-muted-foreground">Revoked</span>
                    <p>{new Date(selectedWs.revoked_at).toLocaleString()}</p>
                  </div>
                )}
              </div>

              {/* Current posture */}
              {(selectedWs.profile_name || selectedWs.autonomy_default || selectedWs.model_tier || selectedWs.tool_allowlist_profile) && (
                <>
                  <Separator />
                  <div>
                    <h4 className="text-sm font-medium mb-2">Current Posture</h4>
                    <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
                      {selectedWs.profile_name && (
                        <div>
                          <span className="text-muted-foreground">Profile</span>
                          <p className="font-mono">{selectedWs.profile_name}</p>
                        </div>
                      )}
                      {selectedWs.autonomy_default && (
                        <div>
                          <span className="text-muted-foreground">Autonomy</span>
                          <p>{selectedWs.autonomy_default}</p>
                        </div>
                      )}
                      {selectedWs.model_tier && (
                        <div>
                          <span className="text-muted-foreground">Model Tier</span>
                          <p>{selectedWs.model_tier}</p>
                        </div>
                      )}
                      {selectedWs.tool_allowlist_profile && (
                        <div>
                          <span className="text-muted-foreground">Tool Profile</span>
                          <p className="font-mono">{selectedWs.tool_allowlist_profile}</p>
                        </div>
                      )}
                    </div>
                  </div>
                </>
              )}

              {/* Posture editor */}
              {showPosture && (
                <>
                  <Separator />
                  <div className="space-y-3">
                    <h4 className="text-sm font-medium">Edit Posture Bindings</h4>
                    <div className="grid grid-cols-2 gap-3">
                      <div className="space-y-1">
                        <Label htmlFor="posture-profile" className="text-xs">Profile name</Label>
                        <Input
                          id="posture-profile"
                          placeholder="e.g. safe_refactor"
                          value={postureProfile}
                          onChange={e => setPostureProfile(e.target.value)}
                          className="text-sm"
                        />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="posture-autonomy" className="text-xs">Autonomy</Label>
                        <Select value={postureAutonomy} onValueChange={setPostureAutonomy}>
                          <SelectTrigger id="posture-autonomy" className="text-sm">
                            <SelectValue placeholder="-- none --" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="none">-- none --</SelectItem>
                            <SelectItem value="OFF">OFF</SelectItem>
                            <SelectItem value="ASSIST">ASSIST</SelectItem>
                            <SelectItem value="FULL">FULL</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="posture-tier" className="text-xs">Model tier</Label>
                        <Input
                          id="posture-tier"
                          placeholder="e.g. standard, premium"
                          value={postureModelTier}
                          onChange={e => setPostureModelTier(e.target.value)}
                          className="text-sm"
                        />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="posture-tools" className="text-xs">Tool profile</Label>
                        <Input
                          id="posture-tools"
                          placeholder="e.g. read_only, full_access"
                          value={postureToolProfile}
                          onChange={e => setPostureToolProfile(e.target.value)}
                          className="text-sm"
                        />
                      </div>
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="posture-notes" className="text-xs">Notes</Label>
                      <Input
                        id="posture-notes"
                        placeholder="Optional notes"
                        value={postureNotes}
                        onChange={e => setPostureNotes(e.target.value)}
                        className="text-sm"
                      />
                    </div>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        onClick={handlePostureSave}
                        disabled={postureMutation.isPending}
                      >
                        {postureMutation.isPending ? "Saving..." : "Save Posture"}
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setShowPosture(false)}>
                        Cancel
                      </Button>
                    </div>
                  </div>
                </>
              )}

              {/* Scan results */}
              {scanResult && (
                <>
                  <Separator />
                  <div className="space-y-3">
                    <h4 className="text-sm font-medium flex items-center gap-2">
                      <ScanSearch className="w-4 h-4" />
                      Scan Results
                    </h4>
                    <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
                      <div>
                        <span className="text-muted-foreground">Risk Tags</span>
                        <div className="flex gap-1 mt-1 flex-wrap">
                          {scanResult.risk_tags?.length ? (
                            scanResult.risk_tags.map(t => <RiskTag key={t} tag={t} />)
                          ) : (
                            <Badge variant="outline" className="bg-emerald-500/10 text-emerald-600">clean</Badge>
                          )}
                        </div>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Suggested Profile</span>
                        <p className="font-mono">{scanResult.suggested_profile || "none"}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Files Scanned</span>
                        <p>{scanResult.file_count ?? "--"}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Inputs Hash</span>
                        <p className="font-mono text-xs">{scanResult.inputs_hash?.substring(0, 16)}...</p>
                      </div>
                    </div>
                    {scanResult.suggested_profile && scanResult.suggested_profile !== "default" && (
                      <div className="flex items-center gap-2 p-2 rounded bg-amber-500/10 text-sm">
                        <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
                        <span className="text-muted-foreground">
                          Suggested posture: <strong className="text-foreground">{scanResult.suggested_profile}</strong>
                        </span>
                        <Button
                          size="sm"
                          variant="outline"
                          className="ml-auto"
                          onClick={() => handleApplyProfile(scanResult.suggested_profile!)}
                          disabled={postureMutation.isPending}
                        >
                          Apply
                        </Button>
                      </div>
                    )}
                  </div>
                </>
              )}
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
