import { useQuery, useMutation } from "@tanstack/react-query";
import { useState } from "react";
import type { SettingsData, OrgSettingsData, User, Group, Role, ApiKey, SecurityPolicy, Notification as NotifType, IpAllowlistEntry, AgentProfile } from "@shared/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter, DialogClose } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog";
import {
  Copy, FolderOpen, Database, GitBranch, Tag, Globe, Flag, Lock,
  Users, Shield, KeyRound, Building2, Bell, FileCheck, Network,
  UserCog, ChevronDown, Search, ShieldCheck, ShieldAlert, Clock,
  CheckCircle, XCircle, AlertTriangle, Server, Eye, Fingerprint,
  Plus, Trash2, Edit, UserPlus, RotateCcw,
  Key, FolderCheck, AlertCircle, ShieldOff, Sparkles
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { apiRequest, queryClient } from "@/lib/queryClient";

function fmt(d: Date | string | null | undefined): string {
  if (!d) return "--";
  const date = typeof d === "string" ? new Date(d) : d;
  return date.toLocaleString();
}

function ago(d: Date | string | null | undefined): string {
  if (!d) return "--";
  const date = typeof d === "string" ? new Date(d) : d;
  const diff = Date.now() - date.getTime();
  if (diff < 60000) return "just now";
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return `${Math.floor(diff / 86400000)}d ago`;
}

const ORG_QUERY_KEY = ["/api/settings/organization"];

function GeneralTab({ data }: { data: SettingsData }) {
  const { toast } = useToast();
  const copyDiagnostics = () => {
    const report = [
      "=== AtlasBridge Diagnostics Report ===",
      `Version: ${data.version}`, `Environment: ${data.environment}`,
      `Config: ${data.configPath}`, `Database: ${data.dbPath}`, `Traces: ${data.tracePath}`,
      "", "Feature Flags:", ...Object.entries(data.featureFlags).map(([k, v]) => `  ${k}: ${v}`),
      "", `Generated: ${new Date().toISOString()}`, "Tokens: [REDACTED]",
    ].join("\n");
    navigator.clipboard.writeText(report).then(() => {
      toast({ title: "Diagnostics copied", description: "Sanitized report copied to clipboard" });
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button variant="secondary" size="sm" onClick={copyDiagnostics} data-testid="button-copy-diagnostics">
          <Copy className="w-3.5 h-3.5 mr-1.5" /> Copy Diagnostics
        </Button>
      </div>
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-sm font-medium">System Configuration</CardTitle></CardHeader>
        <CardContent>
          <dl className="space-y-4">
            {([
              [FolderOpen, "Config Path", data.configPath],
              [Database, "Database Path", data.dbPath],
              [GitBranch, "Trace Path", data.tracePath],
              [Tag, "Version", data.version],
              [Globe, "Environment", data.environment],
            ] as [typeof FolderOpen, string, string][]).map(([IconComp, label, value]) => (
              <div key={label} className="flex items-start justify-between gap-4" data-testid={`setting-${label.toLowerCase().replace(/\s/g, "-")}`}>
                <dt className="flex items-center gap-2 text-sm text-muted-foreground shrink-0">
                  <IconComp className="w-4 h-4" />{label}
                </dt>
                <dd><code className="text-xs font-mono bg-muted px-2 py-1 rounded">{value}</code></dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium flex items-center gap-2"><Flag className="w-4 h-4 text-primary" />Feature Flags</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {Object.entries(data.featureFlags).map(([flag, enabled]) => (
              <div key={flag} className="flex items-center justify-between gap-2 p-2.5 rounded-md bg-muted/50" data-testid={`flag-${flag}`}>
                <span className="text-sm">{flag.replace(/_/g, " ")}</span>
                <Badge variant="secondary" className={`text-[10px] ${enabled ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : "bg-muted text-muted-foreground"}`}>
                  {enabled ? "enabled" : "disabled"}
                </Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function OrgProfileTab({ org }: { org: OrgSettingsData }) {
  const profile = org.organization;
  const seatPct = (profile.usedSeats / profile.maxSeats) * 100;
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-sm font-medium flex items-center gap-2"><Building2 className="w-4 h-4 text-primary" />Organization Profile</CardTitle></CardHeader>
        <CardContent>
          <dl className="space-y-3 text-sm">
            {[["Name", profile.name], ["ID", profile.id], ["Slug", profile.slug], ["Plan", profile.planTier], ["Domain", profile.domain], ["Owner", profile.owner], ["Created", fmt(profile.createdAt)]].map(([l, v]) => (
              <div key={String(l)} className="flex items-center justify-between gap-4">
                <dt className="text-muted-foreground">{String(l)}</dt>
                <dd><code className="text-xs font-mono bg-muted px-2 py-1 rounded">{String(v)}</code></dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-sm font-medium">Seat Allocation</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between text-sm"><span className="text-muted-foreground">Used</span><span className="font-medium">{profile.usedSeats} / {profile.maxSeats}</span></div>
          <Progress value={seatPct} className="h-2" />
          <p className="text-xs text-muted-foreground">{profile.maxSeats - profile.usedSeats} seats available</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-sm font-medium flex items-center gap-2"><Fingerprint className="w-4 h-4 text-primary" />SSO / Identity Provider</CardTitle></CardHeader>
        <CardContent>
          <dl className="space-y-3 text-sm">
            <div className="flex items-center justify-between gap-4"><dt className="text-muted-foreground">Provider</dt><dd><Badge variant="secondary" className="text-[10px]">{org.sso.provider.toUpperCase()}</Badge></dd></div>
            <div className="flex items-center justify-between gap-4"><dt className="text-muted-foreground">Status</dt><dd><Badge variant="secondary" className={`text-[10px] ${org.sso.enabled ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : "bg-red-500/10 text-red-700 dark:text-red-300"}`}>{org.sso.enabled ? "enabled" : "disabled"}</Badge></dd></div>
            <div className="flex items-center justify-between gap-4"><dt className="text-muted-foreground">Entity ID</dt><dd><code className="text-xs font-mono bg-muted px-2 py-1 rounded">{org.sso.entityId}</code></dd></div>
            <div className="flex items-center justify-between gap-4"><dt className="text-muted-foreground">SSO URL</dt><dd><code className="text-xs font-mono bg-muted px-2 py-1 rounded">{org.sso.ssoUrl}</code></dd></div>
            <div className="flex items-center justify-between gap-4"><dt className="text-muted-foreground">Default Role</dt><dd><code className="text-xs font-mono bg-muted px-2 py-1 rounded">{org.sso.defaultRole}</code></dd></div>
            <div className="flex items-center justify-between gap-4"><dt className="text-muted-foreground">Allowed Domains</dt><dd className="flex gap-1 flex-wrap justify-end">{org.sso.allowedDomains.map(d => <Badge key={d} variant="secondary" className="text-[10px]">{d}</Badge>)}</dd></div>
            <div className="flex items-center justify-between gap-4"><dt className="text-muted-foreground">Session Duration</dt><dd><code className="text-xs font-mono bg-muted px-2 py-1 rounded">{org.sso.sessionDuration} min</code></dd></div>
          </dl>
        </CardContent>
      </Card>
    </div>
  );
}

function RbacTab({ org }: { org: OrgSettingsData }) {
  const { toast } = useToast();
  const [expandedRole, setExpandedRole] = useState<number | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newRole, setNewRole] = useState({ name: "", description: "", permissions: "" });
  const [editRole, setEditRole] = useState<Role | null>(null);
  const [editRoleFields, setEditRoleFields] = useState({ name: "", description: "", permissions: "" });
  const [showCreatePerm, setShowCreatePerm] = useState(false);
  const [newPerm, setNewPerm] = useState({ resource: "", actions: "", description: "", category: "" });
  const [editPerm, setEditPerm] = useState<typeof org.permissions[0] | null>(null);
  const [editPermFields, setEditPermFields] = useState({ resource: "", actions: "", description: "", category: "" });

  const createRoleMutation = useMutation({
    mutationFn: (data: any) => apiRequest("POST", "/api/roles", data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ORG_QUERY_KEY }); setShowCreate(false); setNewRole({ name: "", description: "", permissions: "" }); toast({ title: "Role created" }); },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const editRoleMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => apiRequest("PATCH", `/api/roles/${id}`, data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ORG_QUERY_KEY }); setEditRole(null); toast({ title: "Role updated" }); },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const deleteRoleMutation = useMutation({
    mutationFn: (id: number) => apiRequest("DELETE", `/api/roles/${id}`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ORG_QUERY_KEY }); toast({ title: "Role deleted" }); },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const createPermMutation = useMutation({
    mutationFn: (data: any) => apiRequest("POST", "/api/permissions", data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ORG_QUERY_KEY }); setShowCreatePerm(false); setNewPerm({ resource: "", actions: "", description: "", category: "" }); toast({ title: "Permission created" }); },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const editPermMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => apiRequest("PATCH", `/api/permissions/${id}`, data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ORG_QUERY_KEY }); setEditPerm(null); toast({ title: "Permission updated" }); },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const deletePermMutation = useMutation({
    mutationFn: (id: string) => apiRequest("DELETE", `/api/permissions/${id}`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ORG_QUERY_KEY }); toast({ title: "Permission deleted" }); },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const parsePerms = (s: string) => s.split(",").map(p => p.trim()).filter(Boolean);
  const parseActions = (s: string) => s.split(",").map(a => a.trim()).filter(Boolean);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3 flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2"><Shield className="w-4 h-4 text-primary" />RBAC Roles ({org.roles.length})</CardTitle>
          <Dialog open={showCreate} onOpenChange={setShowCreate}>
            <DialogTrigger asChild><Button size="sm" data-testid="button-create-role"><Plus className="w-3.5 h-3.5 mr-1" />Create Role</Button></DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Create Role</DialogTitle></DialogHeader>
              <div className="space-y-4">
                <div><Label>Name</Label><Input value={newRole.name} onChange={e => setNewRole(p => ({ ...p, name: e.target.value }))} data-testid="input-role-name" /></div>
                <div><Label>Description</Label><Input value={newRole.description} onChange={e => setNewRole(p => ({ ...p, description: e.target.value }))} data-testid="input-role-description" /></div>
                <div><Label>Permissions</Label><Input value={newRole.permissions} onChange={e => setNewRole(p => ({ ...p, permissions: e.target.value }))} placeholder="sessions:view, prompts:respond" data-testid="input-role-permissions" /><p className="text-[11px] text-muted-foreground mt-1">Comma-separated permission strings</p></div>
              </div>
              <DialogFooter>
                <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
                <Button onClick={() => createRoleMutation.mutate({ name: newRole.name, description: newRole.description, permissions: parsePerms(newRole.permissions) })} disabled={!newRole.name || createRoleMutation.isPending} data-testid="button-submit-role">
                  {createRoleMutation.isPending ? "Creating..." : "Create"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </CardHeader>
        <CardContent className="space-y-2 p-3">
          {org.roles.map(role => (
            <Collapsible key={role.id} open={expandedRole === role.id} onOpenChange={(open) => setExpandedRole(open ? role.id : null)}>
              <CollapsibleTrigger asChild>
                <div className="flex items-center justify-between gap-2 p-3 rounded-md bg-muted/50 cursor-pointer" data-testid={`role-${role.id}`}>
                  <div className="flex items-center gap-2 min-w-0">
                    <Shield className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                    <span className="text-sm font-medium truncate">{role.name}</span>
                    {role.isSystem && <Badge variant="secondary" className="text-[10px] shrink-0">system</Badge>}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Badge variant="secondary" className="text-[10px]"><Users className="w-2.5 h-2.5 mr-1" />{role.memberCount}</Badge>
                    <div className="flex items-center gap-1" onClick={e => e.stopPropagation()}>
                      <Button variant="ghost" size="sm" className="h-6 w-6 p-0" data-testid={`button-edit-role-${role.id}`} onClick={() => { setEditRole(role); setEditRoleFields({ name: role.name, description: role.description || "", permissions: (role.permissions || []).join(", ") }); }}><Edit className="w-3 h-3" /></Button>
                      <AlertDialog>
                        <AlertDialogTrigger asChild><Button variant="ghost" size="sm" className="h-6 w-6 p-0" data-testid={`button-delete-role-${role.id}`}><Trash2 className="w-3 h-3 text-destructive" /></Button></AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader><AlertDialogTitle>Delete Role</AlertDialogTitle><AlertDialogDescription>Delete "{role.name}"? This cannot be undone.</AlertDialogDescription></AlertDialogHeader>
                          <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={() => deleteRoleMutation.mutate(role.id)}>Delete</AlertDialogAction></AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                    <ChevronDown className={`w-4 h-4 text-muted-foreground transition-transform ${expandedRole === role.id ? "rotate-180" : ""}`} />
                  </div>
                </div>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <div className="px-3 pb-3 pt-2 space-y-3">
                  <p className="text-xs text-muted-foreground">{role.description}</p>
                  <div>
                    <p className="text-xs font-medium text-muted-foreground mb-1.5">Permissions</p>
                    <div className="flex flex-wrap gap-1">
                      {(role.permissions || []).map(perm => <Badge key={perm} variant="secondary" className="text-[10px] font-mono">{perm}</Badge>)}
                    </div>
                  </div>
                  <p className="text-[10px] text-muted-foreground">Created: {fmt(role.createdAt)}</p>
                </div>
              </CollapsibleContent>
            </Collapsible>
          ))}
        </CardContent>
      </Card>

      <Dialog open={!!editRole} onOpenChange={(open) => { if (!open) setEditRole(null); }}>
        <DialogContent>
          <DialogHeader><DialogTitle>Edit Role</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div><Label>Name</Label><Input value={editRoleFields.name} onChange={e => setEditRoleFields(p => ({ ...p, name: e.target.value }))} data-testid="input-edit-role-name" /></div>
            <div><Label>Description</Label><Input value={editRoleFields.description} onChange={e => setEditRoleFields(p => ({ ...p, description: e.target.value }))} data-testid="input-edit-role-description" /></div>
            <div><Label>Permissions</Label><Input value={editRoleFields.permissions} onChange={e => setEditRoleFields(p => ({ ...p, permissions: e.target.value }))} placeholder="sessions:view, prompts:respond" data-testid="input-edit-role-permissions" /><p className="text-[11px] text-muted-foreground mt-1">Comma-separated permission strings</p></div>
          </div>
          <DialogFooter>
            <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
            <Button onClick={() => editRole && editRoleMutation.mutate({ id: editRole.id, data: { name: editRoleFields.name, description: editRoleFields.description, permissions: parsePerms(editRoleFields.permissions) } })} disabled={!editRoleFields.name || editRoleMutation.isPending} data-testid="button-submit-edit-role">
              {editRoleMutation.isPending ? "Saving..." : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Card>
        <CardHeader className="pb-3 flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2"><Eye className="w-4 h-4 text-primary" />Permission Matrix ({org.permissions.length})</CardTitle>
          <Dialog open={showCreatePerm} onOpenChange={setShowCreatePerm}>
            <DialogTrigger asChild><Button size="sm" variant="secondary" data-testid="button-create-perm"><Plus className="w-3.5 h-3.5 mr-1" />Add Permission</Button></DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Add Permission</DialogTitle></DialogHeader>
              <div className="space-y-4">
                <div><Label>Resource</Label><Input value={newPerm.resource} onChange={e => setNewPerm(p => ({ ...p, resource: e.target.value }))} placeholder="e.g. Dashboards" data-testid="input-perm-resource" /></div>
                <div><Label>Actions</Label><Input value={newPerm.actions} onChange={e => setNewPerm(p => ({ ...p, actions: e.target.value }))} placeholder="view, manage, export" data-testid="input-perm-actions" /><p className="text-[11px] text-muted-foreground mt-1">Comma-separated action names</p></div>
                <div><Label>Category</Label><Input value={newPerm.category} onChange={e => setNewPerm(p => ({ ...p, category: e.target.value }))} placeholder="e.g. Operations" data-testid="input-perm-category" /></div>
                <div><Label>Description</Label><Input value={newPerm.description} onChange={e => setNewPerm(p => ({ ...p, description: e.target.value }))} data-testid="input-perm-description" /></div>
              </div>
              <DialogFooter>
                <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
                <Button onClick={() => createPermMutation.mutate({ resource: newPerm.resource, actions: parseActions(newPerm.actions), description: newPerm.description, category: newPerm.category })} disabled={!newPerm.resource || createPermMutation.isPending} data-testid="button-submit-perm">
                  {createPermMutation.isPending ? "Adding..." : "Add"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </CardHeader>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b text-left"><th className="px-4 py-2 font-medium text-muted-foreground text-xs">Resource</th><th className="px-4 py-2 font-medium text-muted-foreground text-xs">Actions</th><th className="px-4 py-2 font-medium text-muted-foreground text-xs hidden md:table-cell">Category</th><th className="px-4 py-2 font-medium text-muted-foreground text-xs w-16"></th></tr></thead>
            <tbody>
              {org.permissions.map(perm => (
                <tr key={perm.id} className="border-b last:border-0" data-testid={`perm-${perm.id}`}>
                  <td className="px-4 py-2 font-medium text-sm">{perm.resource}</td>
                  <td className="px-4 py-2"><div className="flex flex-wrap gap-1">{perm.actions.map(a => <Badge key={a} variant="secondary" className="text-[10px] pointer-events-none cursor-default">{a}</Badge>)}</div></td>
                  <td className="px-4 py-2 hidden md:table-cell text-xs text-muted-foreground">{perm.category}</td>
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-1">
                      <Button variant="ghost" size="sm" className="h-6 w-6 p-0" data-testid={`button-edit-perm-${perm.id}`} onClick={() => { setEditPerm(perm); setEditPermFields({ resource: perm.resource, actions: perm.actions.join(", "), description: perm.description, category: perm.category }); }}><Edit className="w-3 h-3" /></Button>
                      <AlertDialog>
                        <AlertDialogTrigger asChild><Button variant="ghost" size="sm" className="h-6 w-6 p-0" data-testid={`button-delete-perm-${perm.id}`}><Trash2 className="w-3 h-3 text-destructive" /></Button></AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader><AlertDialogTitle>Delete Permission</AlertDialogTitle><AlertDialogDescription>Delete "{perm.resource}" permission? This cannot be undone.</AlertDialogDescription></AlertDialogHeader>
                          <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={() => deletePermMutation.mutate(perm.id)}>Delete</AlertDialogAction></AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Dialog open={!!editPerm} onOpenChange={(open) => { if (!open) setEditPerm(null); }}>
        <DialogContent>
          <DialogHeader><DialogTitle>Edit Permission</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div><Label>Resource</Label><Input value={editPermFields.resource} onChange={e => setEditPermFields(p => ({ ...p, resource: e.target.value }))} data-testid="input-edit-perm-resource" /></div>
            <div><Label>Actions</Label><Input value={editPermFields.actions} onChange={e => setEditPermFields(p => ({ ...p, actions: e.target.value }))} placeholder="view, manage, export" data-testid="input-edit-perm-actions" /><p className="text-[11px] text-muted-foreground mt-1">Comma-separated action names</p></div>
            <div><Label>Category</Label><Input value={editPermFields.category} onChange={e => setEditPermFields(p => ({ ...p, category: e.target.value }))} data-testid="input-edit-perm-category" /></div>
            <div><Label>Description</Label><Input value={editPermFields.description} onChange={e => setEditPermFields(p => ({ ...p, description: e.target.value }))} data-testid="input-edit-perm-description" /></div>
          </div>
          <DialogFooter>
            <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
            <Button onClick={() => editPerm && editPermMutation.mutate({ id: editPerm.id, data: { resource: editPermFields.resource, actions: parseActions(editPermFields.actions), description: editPermFields.description, category: editPermFields.category } })} disabled={!editPermFields.resource || editPermMutation.isPending} data-testid="button-submit-edit-perm">
              {editPermMutation.isPending ? "Saving..." : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function GbacTab({ org }: { org: OrgSettingsData }) {
  const { toast } = useToast();
  const [showCreate, setShowCreate] = useState(false);
  const [newGroup, setNewGroup] = useState({ name: "", description: "", permissionLevel: "read" as string });
  const [editGroup, setEditGroup] = useState<Group | null>(null);
  const [editFields, setEditFields] = useState({ name: "", description: "", permissionLevel: "read" as string });

  const createMutation = useMutation({
    mutationFn: (data: any) => apiRequest("POST", "/api/groups", data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ORG_QUERY_KEY }); setShowCreate(false); setNewGroup({ name: "", description: "", permissionLevel: "read" }); toast({ title: "Group created" }); },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const editMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => apiRequest("PATCH", `/api/groups/${id}`, data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ORG_QUERY_KEY }); setEditGroup(null); toast({ title: "Group updated" }); },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => apiRequest("DELETE", `/api/groups/${id}`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ORG_QUERY_KEY }); toast({ title: "Group deleted" }); },
  });

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3 flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2"><Users className="w-4 h-4 text-primary" />GBAC Groups ({org.groups.length})</CardTitle>
          <Dialog open={showCreate} onOpenChange={setShowCreate}>
            <DialogTrigger asChild><Button size="sm" data-testid="button-create-group"><Plus className="w-3.5 h-3.5 mr-1" />Create Group</Button></DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Create Group</DialogTitle></DialogHeader>
              <div className="space-y-4">
                <div><Label>Name</Label><Input value={newGroup.name} onChange={e => setNewGroup(p => ({ ...p, name: e.target.value }))} data-testid="input-group-name" /></div>
                <div><Label>Description</Label><Input value={newGroup.description} onChange={e => setNewGroup(p => ({ ...p, description: e.target.value }))} data-testid="input-group-description" /></div>
                <div>
                  <Label>Permission Level</Label>
                  <Select value={newGroup.permissionLevel} onValueChange={v => setNewGroup(p => ({ ...p, permissionLevel: v }))}>
                    <SelectTrigger data-testid="select-group-permission"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="read">Read Only</SelectItem>
                      <SelectItem value="read-write">Read & Write</SelectItem>
                      <SelectItem value="admin">Admin</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <DialogFooter>
                <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
                <Button onClick={() => createMutation.mutate(newGroup)} disabled={!newGroup.name || createMutation.isPending} data-testid="button-submit-group">
                  {createMutation.isPending ? "Creating..." : "Create"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </CardHeader>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b text-left"><th className="px-4 py-3 font-medium text-muted-foreground text-xs">Group</th><th className="px-4 py-3 font-medium text-muted-foreground text-xs hidden sm:table-cell">Description</th><th className="px-4 py-3 font-medium text-muted-foreground text-xs">Members</th><th className="px-4 py-3 font-medium text-muted-foreground text-xs">Permission</th><th className="px-4 py-3 font-medium text-muted-foreground text-xs hidden md:table-cell">Roles</th><th className="px-4 py-3 font-medium text-muted-foreground text-xs hidden md:table-cell">Sync</th><th className="px-4 py-3 font-medium text-muted-foreground text-xs w-10"></th></tr></thead>
            <tbody>
              {org.groups.map(group => (
                <tr key={group.id} className="border-b last:border-0" data-testid={`group-${group.id}`}>
                  <td className="px-4 py-2.5 font-medium">{group.name}</td>
                  <td className="px-4 py-2.5 hidden sm:table-cell text-xs text-muted-foreground max-w-[200px] truncate">{group.description}</td>
                  <td className="px-4 py-2.5 text-center"><Badge variant="secondary" className="text-[10px]">{group.memberCount}</Badge></td>
                  <td className="px-4 py-2.5">
                    <Badge variant="secondary" className={`text-[10px] ${group.permissionLevel === "admin" ? "bg-red-500/10 text-red-700 dark:text-red-300" : group.permissionLevel === "read-write" ? "bg-blue-500/10 text-blue-700 dark:text-blue-300" : ""}`}>
                      {group.permissionLevel}
                    </Badge>
                  </td>
                  <td className="px-4 py-2.5 hidden md:table-cell"><div className="flex flex-wrap gap-1">{(group.roles || []).map(r => <Badge key={r} variant="secondary" className="text-[10px]">{r}</Badge>)}</div></td>
                  <td className="px-4 py-2.5 hidden md:table-cell"><Badge variant="secondary" className="text-[10px]">{group.syncSource}</Badge></td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-1">
                      <Button variant="ghost" size="sm" className="h-7 w-7 p-0" data-testid={`button-edit-group-${group.id}`} onClick={() => { setEditGroup(group); setEditFields({ name: group.name, description: group.description || "", permissionLevel: group.permissionLevel }); }}><Edit className="w-3.5 h-3.5" /></Button>
                      <AlertDialog>
                        <AlertDialogTrigger asChild><Button variant="ghost" size="sm" className="h-7 w-7 p-0" data-testid={`button-delete-group-${group.id}`}><Trash2 className="w-3.5 h-3.5 text-destructive" /></Button></AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader><AlertDialogTitle>Delete Group</AlertDialogTitle><AlertDialogDescription>Delete "{group.name}"? This cannot be undone.</AlertDialogDescription></AlertDialogHeader>
                          <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={() => deleteMutation.mutate(group.id)}>Delete</AlertDialogAction></AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Dialog open={!!editGroup} onOpenChange={(open) => { if (!open) setEditGroup(null); }}>
        <DialogContent>
          <DialogHeader><DialogTitle>Edit Group</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div><Label>Name</Label><Input value={editFields.name} onChange={e => setEditFields(p => ({ ...p, name: e.target.value }))} data-testid="input-edit-group-name" /></div>
            <div><Label>Description</Label><Input value={editFields.description} onChange={e => setEditFields(p => ({ ...p, description: e.target.value }))} data-testid="input-edit-group-description" /></div>
            <div>
              <Label>Permission Level</Label>
              <Select value={editFields.permissionLevel} onValueChange={v => setEditFields(p => ({ ...p, permissionLevel: v }))}>
                <SelectTrigger data-testid="select-edit-group-permission"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="read">Read Only</SelectItem>
                  <SelectItem value="read-write">Read & Write</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
            <Button onClick={() => editGroup && editMutation.mutate({ id: editGroup.id, data: editFields })} disabled={!editFields.name || editMutation.isPending} data-testid="button-submit-edit-group">
              {editMutation.isPending ? "Saving..." : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function UsersTab({ org }: { org: OrgSettingsData }) {
  const { toast } = useToast();
  const [search, setSearch] = useState("");
  const [showInvite, setShowInvite] = useState(false);
  const [invite, setInvite] = useState({ username: "", email: "", displayName: "", role: "Viewer" });
  const [editUser, setEditUser] = useState<User | null>(null);
  const [editFields, setEditFields] = useState({ displayName: "", username: "", email: "", role: "", status: "", mfaStatus: "", groups: "" });

  const openEdit = (user: User) => {
    setEditUser(user);
    setEditFields({
      displayName: user.displayName,
      username: user.username,
      email: user.email,
      role: user.role,
      status: user.status,
      mfaStatus: user.mfaStatus,
      groups: (user.groups ?? []).join(", "),
    });
  };

  const inviteMutation = useMutation({
    mutationFn: (data: any) => apiRequest("POST", "/api/users", data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ORG_QUERY_KEY }); setShowInvite(false); setInvite({ username: "", email: "", displayName: "", role: "Viewer" }); toast({ title: "User invited" }); },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const quickUpdateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => apiRequest("PATCH", `/api/users/${id}`, data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ORG_QUERY_KEY }); toast({ title: "User updated" }); },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => apiRequest("PATCH", `/api/users/${id}`, data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ORG_QUERY_KEY }); setEditUser(null); toast({ title: "User updated" }); },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => apiRequest("DELETE", `/api/users/${id}`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ORG_QUERY_KEY }); toast({ title: "User removed" }); },
  });

  const roleOptions = ["Super Admin", "Org Admin", "Security Officer", "Operator", "Viewer", "Compliance Auditor", "Incident Responder", "API Consumer"];
  const statusOptions = ["active", "inactive", "suspended", "pending"];
  const mfaOptions = ["disabled", "enabled", "enforced"];

  const filtered = org.users.filter(u => {
    if (!search) return true;
    const q = search.toLowerCase();
    return u.displayName.toLowerCase().includes(q) || u.username.toLowerCase().includes(q) || u.email.toLowerCase().includes(q) || u.role.toLowerCase().includes(q);
  });

  const statusIcon = (s: string) => {
    switch (s) {
      case "active": return <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" />;
      case "inactive": return <span className="w-2 h-2 rounded-full bg-gray-400 inline-block" />;
      case "suspended": return <span className="w-2 h-2 rounded-full bg-red-500 inline-block" />;
      case "pending": return <span className="w-2 h-2 rounded-full bg-amber-500 inline-block" />;
      default: return null;
    }
  };

  const mfaCls = (m: string) => m === "enforced" ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : m === "enabled" ? "bg-blue-500/10 text-blue-700 dark:text-blue-300" : "bg-muted text-muted-foreground";

  const handleSaveEdit = () => {
    if (!editUser) return;
    const groups = editFields.groups.split(",").map(g => g.trim()).filter(Boolean);
    updateMutation.mutate({ id: editUser.id, data: { ...editFields, groups } });
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-4 flex gap-2 items-center">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input placeholder="Search users..." value={search} onChange={e => setSearch(e.target.value)} className="pl-9" data-testid="input-user-search" />
          </div>
          <Dialog open={showInvite} onOpenChange={setShowInvite}>
            <DialogTrigger asChild><Button size="sm" data-testid="button-invite-user"><UserPlus className="w-3.5 h-3.5 mr-1" />Invite User</Button></DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Invite User</DialogTitle></DialogHeader>
              <div className="space-y-4">
                <div><Label>Display Name</Label><Input value={invite.displayName} onChange={e => setInvite(p => ({ ...p, displayName: e.target.value }))} data-testid="input-invite-name" /></div>
                <div><Label>Username</Label><Input value={invite.username} onChange={e => setInvite(p => ({ ...p, username: e.target.value }))} data-testid="input-invite-username" /></div>
                <div><Label>Email</Label><Input type="email" value={invite.email} onChange={e => setInvite(p => ({ ...p, email: e.target.value }))} data-testid="input-invite-email" /></div>
                <div>
                  <Label>Role</Label>
                  <Select value={invite.role} onValueChange={v => setInvite(p => ({ ...p, role: v }))}>
                    <SelectTrigger data-testid="select-invite-role"><SelectValue /></SelectTrigger>
                    <SelectContent>{roleOptions.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              </div>
              <DialogFooter>
                <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
                <Button onClick={() => inviteMutation.mutate(invite)} disabled={!invite.username || !invite.email || !invite.displayName || inviteMutation.isPending} data-testid="button-submit-invite">
                  {inviteMutation.isPending ? "Inviting..." : "Send Invite"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </CardContent>
      </Card>

      {/* Full edit dialog */}
      <Dialog open={editUser !== null} onOpenChange={open => { if (!open) setEditUser(null); }}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Edit User</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2 sm:col-span-1">
              <Label>Display Name</Label>
              <Input value={editFields.displayName} onChange={e => setEditFields(p => ({ ...p, displayName: e.target.value }))} data-testid="input-edit-displayname" />
            </div>
            <div className="col-span-2 sm:col-span-1">
              <Label>Username</Label>
              <Input value={editFields.username} onChange={e => setEditFields(p => ({ ...p, username: e.target.value }))} data-testid="input-edit-username" />
            </div>
            <div className="col-span-2">
              <Label>Email</Label>
              <Input type="email" value={editFields.email} onChange={e => setEditFields(p => ({ ...p, email: e.target.value }))} data-testid="input-edit-email" />
            </div>
            <div>
              <Label>Role</Label>
              <Select value={editFields.role} onValueChange={v => setEditFields(p => ({ ...p, role: v }))}>
                <SelectTrigger data-testid="select-edit-role"><SelectValue /></SelectTrigger>
                <SelectContent>{roleOptions.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label>Status</Label>
              <Select value={editFields.status} onValueChange={v => setEditFields(p => ({ ...p, status: v }))}>
                <SelectTrigger data-testid="select-edit-status"><SelectValue /></SelectTrigger>
                <SelectContent>{statusOptions.map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label>MFA</Label>
              <Select value={editFields.mfaStatus} onValueChange={v => setEditFields(p => ({ ...p, mfaStatus: v }))}>
                <SelectTrigger data-testid="select-edit-mfa"><SelectValue /></SelectTrigger>
                <SelectContent>{mfaOptions.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label>Groups <span className="text-muted-foreground text-xs">(comma-separated)</span></Label>
              <Input value={editFields.groups} onChange={e => setEditFields(p => ({ ...p, groups: e.target.value }))} placeholder="e.g. platform, security" data-testid="input-edit-groups" />
            </div>
          </div>
          <DialogFooter className="mt-2">
            <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
            <Button onClick={handleSaveEdit} disabled={updateMutation.isPending} data-testid="button-save-edit-user">
              {updateMutation.isPending ? "Saving..." : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-sm font-medium flex items-center gap-2"><UserCog className="w-4 h-4 text-primary" />Users ({filtered.length})</CardTitle></CardHeader>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b text-left"><th className="px-4 py-2 font-medium text-muted-foreground text-xs">User</th><th className="px-4 py-2 font-medium text-muted-foreground text-xs">Role</th><th className="px-4 py-2 font-medium text-muted-foreground text-xs">Status</th><th className="px-4 py-2 font-medium text-muted-foreground text-xs hidden sm:table-cell">MFA</th><th className="px-4 py-2 font-medium text-muted-foreground text-xs hidden lg:table-cell">Last Active</th><th className="px-4 py-2 font-medium text-muted-foreground text-xs w-28">Actions</th></tr></thead>
            <tbody>
              {filtered.map(user => (
                <tr key={user.id} className="border-b last:border-0" data-testid={`user-${user.id}`}>
                  <td className="px-4 py-2.5"><div><p className="font-medium text-sm">{user.displayName}</p><p className="text-xs text-muted-foreground font-mono">@{user.username}</p><p className="text-xs text-muted-foreground">{user.email}</p></div></td>
                  <td className="px-4 py-2.5">
                    <Select value={user.role} onValueChange={v => quickUpdateMutation.mutate({ id: user.id, data: { role: v } })} disabled={quickUpdateMutation.isPending}>
                      <SelectTrigger className="h-7 text-xs w-32" data-testid={`select-role-${user.id}`}><SelectValue /></SelectTrigger>
                      <SelectContent>{roleOptions.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
                    </Select>
                  </td>
                  <td className="px-4 py-2.5"><span className="flex items-center gap-1.5 text-xs">{statusIcon(user.status)} {user.status}</span></td>
                  <td className="px-4 py-2.5 hidden sm:table-cell"><Badge variant="secondary" className={`text-[10px] ${mfaCls(user.mfaStatus)}`}>{user.mfaStatus}</Badge></td>
                  <td className="px-4 py-2.5 hidden lg:table-cell text-xs text-muted-foreground">{ago(user.lastActive)}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-1">
                      <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => openEdit(user)} data-testid={`button-edit-user-${user.id}`}>
                        <Edit className="w-3.5 h-3.5" />
                      </Button>
                      <AlertDialog>
                        <AlertDialogTrigger asChild><Button variant="ghost" size="sm" className="h-7 w-7 p-0" data-testid={`button-delete-user-${user.id}`}><Trash2 className="w-3.5 h-3.5 text-destructive" /></Button></AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader><AlertDialogTitle>Remove User</AlertDialogTitle><AlertDialogDescription>Remove {user.displayName}? This cannot be undone.</AlertDialogDescription></AlertDialogHeader>
                          <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={() => deleteMutation.mutate(user.id)}>Remove</AlertDialogAction></AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function ApiKeysTab({ org }: { org: OrgSettingsData }) {
  const { toast } = useToast();
  const [showCreate, setShowCreate] = useState(false);
  const [newKey, setNewKey] = useState({ name: "", rateLimit: 100, createdBy: "admin" });
  const [rotatedKey, setRotatedKey] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: (data: any) => apiRequest("POST", "/api/api-keys", data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ORG_QUERY_KEY }); setShowCreate(false); setNewKey({ name: "", rateLimit: 100, createdBy: "admin" }); toast({ title: "API key created" }); },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const revokeMutation = useMutation({
    mutationFn: (id: number) => apiRequest("PATCH", `/api/api-keys/${id}`, { status: "revoked" }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ORG_QUERY_KEY }); toast({ title: "Key revoked" }); },
  });

  const rotateMutation = useMutation({
    mutationFn: (id: number) => apiRequest("POST", `/api/api-keys/${id}/rotate`),
    onSuccess: (data: any) => { queryClient.invalidateQueries({ queryKey: ORG_QUERY_KEY }); setRotatedKey(data.newKey); },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const deleteIpMutation = useMutation({
    mutationFn: (id: number) => apiRequest("DELETE", `/api/ip-allowlist/${id}`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ORG_QUERY_KEY }); toast({ title: "IP entry removed" }); },
  });

  const [newIp, setNewIp] = useState({ cidr: "", label: "" });
  const [showAddIp, setShowAddIp] = useState(false);
  const addIpMutation = useMutation({
    mutationFn: (data: any) => apiRequest("POST", "/api/ip-allowlist", data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ORG_QUERY_KEY }); setShowAddIp(false); setNewIp({ cidr: "", label: "" }); toast({ title: "IP entry added" }); },
  });

  const statusCls = (s: string) => s === "active" ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : s === "revoked" ? "bg-red-500/10 text-red-700 dark:text-red-300" : "bg-muted text-muted-foreground";

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3 flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2"><KeyRound className="w-4 h-4 text-primary" />API Keys ({org.apiKeys.length})</CardTitle>
          <Dialog open={showCreate} onOpenChange={setShowCreate}>
            <DialogTrigger asChild><Button size="sm" data-testid="button-create-apikey"><Plus className="w-3.5 h-3.5 mr-1" />Create Key</Button></DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Create API Key</DialogTitle></DialogHeader>
              <div className="space-y-4">
                <div><Label>Name</Label><Input value={newKey.name} onChange={e => setNewKey(p => ({ ...p, name: e.target.value }))} data-testid="input-apikey-name" /></div>
                <div><Label>Rate Limit (req/min)</Label><Input type="number" value={newKey.rateLimit} onChange={e => setNewKey(p => ({ ...p, rateLimit: parseInt(e.target.value) || 100 }))} data-testid="input-apikey-ratelimit" /></div>
              </div>
              <DialogFooter>
                <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
                <Button onClick={() => createMutation.mutate(newKey)} disabled={!newKey.name || createMutation.isPending} data-testid="button-submit-apikey">
                  {createMutation.isPending ? "Creating..." : "Create"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </CardHeader>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b text-left"><th className="px-4 py-2 font-medium text-muted-foreground text-xs">Name</th><th className="px-4 py-2 font-medium text-muted-foreground text-xs">Prefix</th><th className="px-4 py-2 font-medium text-muted-foreground text-xs">Status</th><th className="px-4 py-2 font-medium text-muted-foreground text-xs hidden md:table-cell">Rate Limit</th><th className="px-4 py-2 font-medium text-muted-foreground text-xs hidden lg:table-cell">Last Used</th><th className="px-4 py-2 font-medium text-muted-foreground text-xs w-20">Actions</th></tr></thead>
            <tbody>
              {org.apiKeys.map(key => (
                <tr key={key.id} className="border-b last:border-0" data-testid={`apikey-${key.id}`}>
                  <td className="px-4 py-2.5 font-medium">{key.name}</td>
                  <td className="px-4 py-2.5"><code className="text-[11px] font-mono bg-muted px-1.5 py-0.5 rounded">{key.prefix}[REDACTED]</code></td>
                  <td className="px-4 py-2.5"><Badge variant="secondary" className={`text-[10px] ${statusCls(key.status)}`}>{key.status}</Badge></td>
                  <td className="px-4 py-2.5 hidden md:table-cell text-xs text-muted-foreground">{key.rateLimit}/min</td>
                  <td className="px-4 py-2.5 hidden lg:table-cell text-xs text-muted-foreground">{ago(key.lastUsed)}</td>
                  <td className="px-4 py-2.5">
                    {key.status === "active" && (
                      <div className="flex items-center gap-1">
                        <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => rotateMutation.mutate(key.id)} disabled={rotateMutation.isPending} data-testid={`button-rotate-${key.id}`}><RotateCcw className="w-3 h-3 mr-1" />Rotate</Button>
                        <Button variant="ghost" size="sm" className="h-7 px-2 text-xs text-destructive" onClick={() => revokeMutation.mutate(key.id)} data-testid={`button-revoke-${key.id}`}>Revoke</Button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card>
        <CardHeader className="pb-3 flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2"><Network className="w-4 h-4 text-primary" />IP Allowlist ({org.ipAllowlist.length})</CardTitle>
          <Dialog open={showAddIp} onOpenChange={setShowAddIp}>
            <DialogTrigger asChild><Button size="sm" variant="secondary" data-testid="button-add-ip"><Plus className="w-3.5 h-3.5 mr-1" />Add IP</Button></DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Add IP Range</DialogTitle></DialogHeader>
              <div className="space-y-4">
                <div><Label>CIDR</Label><Input placeholder="10.0.0.0/8" value={newIp.cidr} onChange={e => setNewIp(p => ({ ...p, cidr: e.target.value }))} data-testid="input-ip-cidr" /></div>
                <div><Label>Label</Label><Input value={newIp.label} onChange={e => setNewIp(p => ({ ...p, label: e.target.value }))} data-testid="input-ip-label" /></div>
              </div>
              <DialogFooter>
                <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
                <Button onClick={() => addIpMutation.mutate({ ...newIp, addedBy: "admin" })} disabled={!newIp.cidr || !newIp.label || addIpMutation.isPending} data-testid="button-submit-ip">Add</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </CardHeader>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b text-left"><th className="px-4 py-2 font-medium text-muted-foreground text-xs">CIDR</th><th className="px-4 py-2 font-medium text-muted-foreground text-xs">Label</th><th className="px-4 py-2 font-medium text-muted-foreground text-xs hidden sm:table-cell">Added By</th><th className="px-4 py-2 font-medium text-muted-foreground text-xs w-10"></th></tr></thead>
            <tbody>
              {org.ipAllowlist.map(ip => (
                <tr key={ip.id} className="border-b last:border-0" data-testid={`ip-${ip.id}`}>
                  <td className="px-4 py-2.5"><code className="text-[11px] font-mono bg-muted px-1.5 py-0.5 rounded">{ip.cidr}</code></td>
                  <td className="px-4 py-2.5 text-sm">{ip.label}</td>
                  <td className="px-4 py-2.5 hidden sm:table-cell text-xs text-muted-foreground">{ip.addedBy}</td>
                  <td className="px-4 py-2.5"><Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => deleteIpMutation.mutate(ip.id)} data-testid={`button-delete-ip-${ip.id}`}><Trash2 className="w-3.5 h-3.5 text-destructive" /></Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Dialog open={!!rotatedKey} onOpenChange={(open) => { if (!open) setRotatedKey(null); }}>
        <DialogContent>
          <DialogHeader><DialogTitle>New API Key</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">Copy this key now — it will not be shown again.</p>
          <div className="flex items-center gap-2">
            <code className="flex-1 text-xs font-mono bg-muted px-3 py-2 rounded break-all">{rotatedKey}</code>
            <Button size="sm" variant="outline" onClick={() => { if (rotatedKey) navigator.clipboard.writeText(rotatedKey); toast({ title: "Copied" }); }} data-testid="button-copy-rotated-key"><Copy className="w-3.5 h-3.5" /></Button>
          </div>
          <DialogFooter><DialogClose asChild><Button>Done</Button></DialogClose></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function SecurityTab({ org }: { org: OrgSettingsData }) {
  const { toast } = useToast();
  const categories = Array.from(new Set(org.securityPolicies.map(p => p.category)));

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => apiRequest("PATCH", `/api/security-policies/${id}`, { enabled }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ORG_QUERY_KEY }); toast({ title: "Policy updated" }); },
  });

  const updateValueMutation = useMutation({
    mutationFn: ({ id, value }: { id: number; value: string }) => apiRequest("PATCH", `/api/security-policies/${id}`, { value }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ORG_QUERY_KEY }); toast({ title: "Policy value updated" }); },
  });

  const [editingPolicy, setEditingPolicy] = useState<SecurityPolicy | null>(null);
  const [editValue, setEditValue] = useState("");

  const severityIcon = (s: string) => {
    switch (s) {
      case "critical": return <ShieldAlert className="w-3.5 h-3.5 text-red-600 dark:text-red-400" />;
      case "warning": return <AlertTriangle className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />;
      default: return <ShieldCheck className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />;
    }
  };

  return (
    <div className="space-y-4">
      {categories.map(category => (
        <Card key={category}>
          <CardHeader className="pb-3"><CardTitle className="text-sm font-medium">{category}</CardTitle></CardHeader>
          <CardContent className="space-y-2 p-3">
            {org.securityPolicies.filter(p => p.category === category).map(policy => (
              <div key={policy.id} className="flex items-start gap-3 p-3 rounded-md bg-muted/50" data-testid={`policy-${policy.id}`}>
                <div className="mt-0.5 shrink-0">{severityIcon(policy.severity)}</div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium">{policy.name}</span>
                    <Switch checked={policy.enabled} onCheckedChange={(checked) => toggleMutation.mutate({ id: policy.id, enabled: checked })} data-testid={`switch-policy-${policy.id}`} />
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">{policy.description}</p>
                  <div className="mt-1.5 flex items-center gap-2">
                    <code className="text-[11px] font-mono bg-muted px-1.5 py-0.5 rounded">{policy.value}</code>
                    <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px]" onClick={() => { setEditingPolicy(policy); setEditValue(policy.value); }} data-testid={`button-edit-policy-${policy.id}`}>
                      <Edit className="w-3 h-3 mr-1" />Edit
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      ))}

      <Dialog open={!!editingPolicy} onOpenChange={(open) => { if (!open) setEditingPolicy(null); }}>
        <DialogContent>
          <DialogHeader><DialogTitle>Edit Policy: {editingPolicy?.name}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div><Label>Value</Label><Input value={editValue} onChange={e => setEditValue(e.target.value)} data-testid="input-policy-value" /></div>
          </div>
          <DialogFooter>
            <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
            <Button onClick={() => { if (editingPolicy) { updateValueMutation.mutate({ id: editingPolicy.id, value: editValue }); setEditingPolicy(null); } }} data-testid="button-save-policy">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-sm font-medium flex items-center gap-2"><Server className="w-4 h-4 text-primary" />Session Policy</CardTitle></CardHeader>
        <CardContent>
          <dl className="space-y-3 text-sm">
            {[
              ["Max Concurrent Sessions", String(org.sessionPolicy.maxConcurrentSessions)],
              ["Session Timeout", `${org.sessionPolicy.sessionTimeoutMinutes} min`],
              ["Inactivity Timeout", `${org.sessionPolicy.inactivityTimeoutMinutes} min`],
              ["Auto-Terminate on Escalation", org.sessionPolicy.autoTerminateOnEscalation ? "Yes" : "No"],
              ["Require Approval Above Risk", org.sessionPolicy.requireApprovalAboveRisk],
              ["Max Escalations per Session", String(org.sessionPolicy.maxEscalationsPerSession)],
              ["Record All Sessions", org.sessionPolicy.recordAllSessions ? "Yes" : "No"],
              ["Risk Auto-Escalation", `${(org.sessionPolicy.riskAutoEscalationThreshold * 100).toFixed(0)}%`],
            ].map(([l, v]) => (
              <div key={String(l)} className="flex items-center justify-between gap-4"><dt className="text-muted-foreground">{String(l)}</dt><dd><code className="text-xs font-mono bg-muted px-2 py-1 rounded">{String(v)}</code></dd></div>
            ))}
          </dl>
          <div className="mt-4 space-y-2">
            <p className="text-xs font-medium text-muted-foreground">Allowed Tools</p>
            <div className="flex flex-wrap gap-1">{org.sessionPolicy.allowedTools.map(t => <Badge key={t} variant="secondary" className="text-[10px]">{t}</Badge>)}</div>
            <p className="text-xs font-medium text-muted-foreground mt-3">Blocked Patterns</p>
            <div className="flex flex-wrap gap-1">{org.sessionPolicy.blockedTools.map(t => <Badge key={t} variant="secondary" className="text-[10px] bg-red-500/10 text-red-700 dark:text-red-300">{t}</Badge>)}</div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function ComplianceTab({ org }: { org: OrgSettingsData }) {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-sm font-medium flex items-center gap-2"><FileCheck className="w-4 h-4 text-primary" />Compliance Configuration</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="text-xs font-medium text-muted-foreground mb-2">Active Frameworks</p>
            <div className="flex flex-wrap gap-2">{org.compliance.frameworks.map(f => <Badge key={f} variant="secondary" className="text-xs bg-blue-500/10 text-blue-700 dark:text-blue-300">{f}</Badge>)}</div>
          </div>
          <dl className="space-y-3 text-sm pt-2 border-t">
            {[["Audit Retention", `${org.compliance.auditRetentionDays} days`], ["Trace Retention", `${org.compliance.traceRetentionDays} days`], ["Session Retention", `${org.compliance.sessionRetentionDays} days`], ["Data Residency", org.compliance.dataResidency], ["Last Audit", fmt(org.compliance.lastAuditDate)], ["Next Audit", fmt(org.compliance.nextAuditDate)]].map(([l, v]) => (
              <div key={String(l)} className="flex items-center justify-between gap-4"><dt className="text-muted-foreground">{String(l)}</dt><dd><code className="text-xs font-mono bg-muted px-2 py-1 rounded">{String(v)}</code></dd></div>
            ))}
          </dl>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 border-t">
            {([["Encryption at Rest", org.compliance.encryptionAtRest], ["Encryption in Transit", org.compliance.encryptionInTransit], ["Auto-Redaction", org.compliance.autoRedaction], ["DLP Enabled", org.compliance.dlpEnabled]] as [string, boolean][]).map(([l, e]) => (
              <div key={l} className="flex items-center gap-2 p-2 rounded-md bg-muted/50">
                {e ? <CheckCircle className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400 shrink-0" /> : <XCircle className="w-3.5 h-3.5 text-red-600 dark:text-red-400 shrink-0" />}
                <span className="text-xs">{l}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function NotificationsTab({ org }: { org: OrgSettingsData }) {
  const { toast } = useToast();
  const [showCreate, setShowCreate] = useState(false);
  const [newNotif, setNewNotif] = useState({ channel: "slack", name: "", destination: "", minSeverity: "info", events: [] as string[] });

  const createMutation = useMutation({
    mutationFn: (data: any) => apiRequest("POST", "/api/notifications", data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ORG_QUERY_KEY }); setShowCreate(false); toast({ title: "Channel created" }); },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => apiRequest("PATCH", `/api/notifications/${id}`, { enabled }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ORG_QUERY_KEY }); },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => apiRequest("DELETE", `/api/notifications/${id}`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ORG_QUERY_KEY }); toast({ title: "Channel removed" }); },
  });

  const channelBadge = (ch: string) => {
    const cls: Record<string, string> = { slack: "bg-purple-500/10 text-purple-700 dark:text-purple-300", email: "bg-blue-500/10 text-blue-700 dark:text-blue-300", pagerduty: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300", webhook: "bg-orange-500/10 text-orange-700 dark:text-orange-300", opsgenie: "bg-cyan-500/10 text-cyan-700 dark:text-cyan-300" };
    return <Badge variant="secondary" className={`text-[10px] ${cls[ch] || ""}`}>{ch}</Badge>;
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3 flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2"><Bell className="w-4 h-4 text-primary" />Notification Channels ({org.notifications.length})</CardTitle>
          <Dialog open={showCreate} onOpenChange={setShowCreate}>
            <DialogTrigger asChild><Button size="sm" data-testid="button-create-notification"><Plus className="w-3.5 h-3.5 mr-1" />Add Channel</Button></DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Add Notification Channel</DialogTitle></DialogHeader>
              <div className="space-y-4">
                <div>
                  <Label>Channel Type</Label>
                  <Select value={newNotif.channel} onValueChange={v => setNewNotif(p => ({ ...p, channel: v }))}>
                    <SelectTrigger data-testid="select-notif-channel"><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="slack">Slack</SelectItem><SelectItem value="email">Email</SelectItem><SelectItem value="webhook">Webhook</SelectItem><SelectItem value="pagerduty">PagerDuty</SelectItem><SelectItem value="opsgenie">OpsGenie</SelectItem></SelectContent>
                  </Select>
                </div>
                <div><Label>Name</Label><Input value={newNotif.name} onChange={e => setNewNotif(p => ({ ...p, name: e.target.value }))} data-testid="input-notif-name" /></div>
                <div><Label>Destination</Label><Input value={newNotif.destination} onChange={e => setNewNotif(p => ({ ...p, destination: e.target.value }))} placeholder={newNotif.channel === "slack" ? "#channel-name" : newNotif.channel === "email" ? "team@company.com" : "https://..."} data-testid="input-notif-destination" /></div>
              </div>
              <DialogFooter>
                <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
                <Button onClick={() => createMutation.mutate(newNotif)} disabled={!newNotif.name || !newNotif.destination || createMutation.isPending} data-testid="button-submit-notification">Add</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </CardHeader>
        <CardContent className="space-y-2 p-3">
          {org.notifications.map(notif => (
            <div key={notif.id} className="p-3 rounded-md bg-muted/50 space-y-2" data-testid={`notif-${notif.id}`}>
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-2">
                  {channelBadge(notif.channel)}
                  <span className="text-sm font-medium">{notif.name}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Switch checked={notif.enabled} onCheckedChange={(checked) => toggleMutation.mutate({ id: notif.id, enabled: checked })} data-testid={`switch-notif-${notif.id}`} />
                  <AlertDialog>
                    <AlertDialogTrigger asChild><Button variant="ghost" size="sm" className="h-7 w-7 p-0" data-testid={`button-delete-notif-${notif.id}`}><Trash2 className="w-3.5 h-3.5 text-destructive" /></Button></AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader><AlertDialogTitle>Remove Channel</AlertDialogTitle><AlertDialogDescription>Remove "{notif.name}"?</AlertDialogDescription></AlertDialogHeader>
                      <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={() => deleteMutation.mutate(notif.id)}>Remove</AlertDialogAction></AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </div>
              <code className="text-[11px] font-mono bg-muted px-1.5 py-0.5 rounded">{notif.destination}</code>
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="flex flex-wrap gap-1">{(notif.events || []).slice(0, 3).map(e => <Badge key={e} variant="secondary" className="text-[10px] font-mono">{e}</Badge>)}{(notif.events || []).length > 3 && <Badge variant="secondary" className="text-[10px]">+{(notif.events || []).length - 3}</Badge>}</div>
                <div className="flex items-center gap-1 text-[10px] text-muted-foreground shrink-0"><Clock className="w-3 h-3" />{ago(notif.lastDelivered)}</div>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Providers tab
// ---------------------------------------------------------------------------

interface ProviderConfig {
  provider: string;
  status: "configured" | "validated" | "invalid";
  key_prefix: string | null;
  configured_at: string | null;
  validated_at: string | null;
  last_error: string | null;
}

const PROVIDERS_QUERY_KEY = ["/api/providers"];
const SUPPORTED_PROVIDERS = ["openai", "anthropic", "gemini"] as const;
type SupportedProvider = typeof SUPPORTED_PROVIDERS[number];
const PROVIDER_INFO: Record<SupportedProvider, { label: string; keyHint: string }> = {
  openai: { label: "OpenAI", keyHint: "sk-…" },
  anthropic: { label: "Anthropic", keyHint: "sk-ant-…" },
  gemini: { label: "Google Gemini", keyHint: "AIza…" },
};

function ProviderStatusBadge({ status }: { status: string }) {
  if (status === "validated") return <Badge className="bg-emerald-600 text-white gap-1"><CheckCircle className="w-3 h-3" />Validated</Badge>;
  if (status === "configured") return <Badge variant="secondary" className="gap-1"><AlertCircle className="w-3 h-3" />Configured</Badge>;
  return <Badge variant="destructive" className="gap-1"><XCircle className="w-3 h-3" />Invalid</Badge>;
}

function ProviderCard({ provider, config }: { provider: SupportedProvider; config: ProviderConfig | undefined }) {
  const { toast } = useToast();
  const info = PROVIDER_INFO[provider];
  const [keyValue, setKeyValue] = useState("");
  const [showInput, setShowInput] = useState(false);

  const saveMutation = useMutation({
    mutationFn: (key: string) => apiRequest("POST", "/api/providers", { provider, key }),
    onSuccess: () => {
      toast({ title: "Key saved", description: `${info.label} key stored securely.` });
      queryClient.invalidateQueries({ queryKey: PROVIDERS_QUERY_KEY });
      setKeyValue(""); setShowInput(false);
    },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const validateMutation = useMutation({
    mutationFn: () => apiRequest("POST", `/api/providers/${provider}/validate`),
    onSuccess: () => { toast({ title: "Validated", description: `${info.label} key is valid.` }); queryClient.invalidateQueries({ queryKey: PROVIDERS_QUERY_KEY }); },
    onError: (e: Error) => toast({ title: "Validation failed", description: e.message, variant: "destructive" }),
  });

  const removeMutation = useMutation({
    mutationFn: () => apiRequest("DELETE", `/api/providers/${provider}`),
    onSuccess: () => { toast({ title: "Removed", description: `${info.label} key removed.` }); queryClient.invalidateQueries({ queryKey: PROVIDERS_QUERY_KEY }); },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2"><Key className="w-4 h-4 text-muted-foreground" />{info.label}</CardTitle>
          {config && <ProviderStatusBadge status={config.status} />}
        </div>
        {config?.key_prefix && <p className="font-mono text-xs text-muted-foreground mt-1">Key: {config.key_prefix}</p>}
        {config?.last_error && config.status === "invalid" && <p className="text-destructive text-xs mt-1">{config.last_error}</p>}
      </CardHeader>
      <CardContent className="space-y-3">
        {showInput ? (
          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">API key — stored securely, never displayed again</Label>
            <Input type="password" placeholder={info.keyHint} value={keyValue} onChange={e => setKeyValue(e.target.value)} onKeyDown={e => e.key === "Enter" && keyValue && saveMutation.mutate(keyValue)} className="font-mono text-sm" />
            <div className="flex gap-2">
              <Button size="sm" onClick={() => keyValue && saveMutation.mutate(keyValue)} disabled={!keyValue || saveMutation.isPending}>{saveMutation.isPending ? "Saving…" : "Save"}</Button>
              <Button size="sm" variant="ghost" onClick={() => { setShowInput(false); setKeyValue(""); }}>Cancel</Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant={config ? "outline" : "default"} onClick={() => setShowInput(true)}>{config ? "Replace key" : "Add key"}</Button>
            {config && (
              <>
                <Button size="sm" variant="outline" onClick={() => validateMutation.mutate()} disabled={validateMutation.isPending}>{validateMutation.isPending ? "Validating…" : "Validate"}</Button>
                <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={() => removeMutation.mutate()} disabled={removeMutation.isPending}><Trash2 className="w-3.5 h-3.5 mr-1" />Remove</Button>
              </>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ProvidersTab() {
  const { data: providers, isLoading } = useQuery<ProviderConfig[]>({ queryKey: PROVIDERS_QUERY_KEY, refetchInterval: 15_000 });
  const configMap = Object.fromEntries((providers ?? []).map(p => [p.provider, p])) as Record<string, ProviderConfig>;

  return (
    <div className="space-y-4">
      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{SUPPORTED_PROVIDERS.map(p => <Skeleton key={p} className="h-40 w-full" />)}</div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {SUPPORTED_PROVIDERS.map(p => <ProviderCard key={p} provider={p} config={configMap[p]} />)}
        </div>
      )}
      <Card className="border-dashed">
        <CardContent className="p-4">
          <p className="text-xs text-muted-foreground"><strong>Storage:</strong> API keys are stored in your OS keychain (macOS Keychain, Linux Secret Service). Only a short prefix is shown. Keys are never transmitted to AtlasBridge servers and never appear in logs or audit traces.</p>
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Workspaces tab
// ---------------------------------------------------------------------------

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

const WORKSPACES_QUERY_KEY = ["/api/workspaces"];

function WorkspacesTab() {
  const { toast } = useToast();
  const { data: workspaces, isLoading } = useQuery<WorkspaceRecord[]>({ queryKey: WORKSPACES_QUERY_KEY, refetchInterval: 10_000 });
  const [newPath, setNewPath] = useState("");
  const [showAdd, setShowAdd] = useState(false);

  const trustMutation = useMutation({
    mutationFn: (path: string) => apiRequest("POST", "/api/workspaces/trust", { path }),
    onSuccess: () => { toast({ title: "Trust granted", description: "Workspace marked as trusted." }); queryClient.invalidateQueries({ queryKey: WORKSPACES_QUERY_KEY }); setNewPath(""); setShowAdd(false); },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const revokeMutation = useMutation({
    mutationFn: (path: string) => apiRequest("DELETE", "/api/workspaces/trust", { path }),
    onSuccess: () => { toast({ title: "Trust revoked" }); queryClient.invalidateQueries({ queryKey: WORKSPACES_QUERY_KEY }); },
    onError: (e: Error) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" variant="outline" onClick={() => setShowAdd(!showAdd)}><Plus className="w-4 h-4 mr-1.5" />Grant Trust</Button>
      </div>

      {showAdd && (
        <Card>
          <CardHeader className="pb-3"><CardTitle className="text-sm font-medium">Grant workspace trust</CardTitle></CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-3">Enter the absolute path of the workspace directory. Future sessions using this path will auto-approve without a channel prompt.</p>
            <div className="flex gap-2">
              <Input placeholder="/path/to/workspace" value={newPath} onChange={e => setNewPath(e.target.value)} onKeyDown={e => e.key === "Enter" && trustMutation.mutate(newPath.trim())} className="font-mono text-sm" />
              <Button onClick={() => trustMutation.mutate(newPath.trim())} disabled={!newPath.trim() || trustMutation.isPending}>{trustMutation.isPending ? "Saving…" : "Grant"}</Button>
              <Button variant="ghost" onClick={() => { setShowAdd(false); setNewPath(""); }}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-sm font-medium flex items-center gap-2"><FolderCheck className="w-4 h-4 text-muted-foreground" />Recorded workspaces</CardTitle></CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-4 space-y-2">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
          ) : !workspaces || workspaces.length === 0 ? (
            <div className="p-6 text-center text-sm text-muted-foreground">No workspaces recorded yet. Grant trust to a directory above or start a session that requests workspace access.</div>
          ) : (
            <div className="divide-y">
              {workspaces.map(ws => {
                const isTrusted = Boolean(ws.trusted);
                return (
                  <div key={ws.id} className="flex items-center justify-between gap-3 px-4 py-3">
                    <div className="flex items-center gap-3 min-w-0">
                      {isTrusted ? <ShieldCheck className="w-4 h-4 text-emerald-500 shrink-0" /> : <ShieldOff className="w-4 h-4 text-muted-foreground shrink-0" />}
                      <div className="min-w-0">
                        <p className="text-sm font-mono truncate" title={ws.path}>{ws.path}</p>
                        <p className="text-xs text-muted-foreground">{ws.actor ? `via ${ws.actor}` : ""}{ws.granted_at ? ` · ${new Date(ws.granted_at).toLocaleString()}` : ""}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Badge variant={isTrusted ? "default" : "secondary"} className={isTrusted ? "bg-emerald-600 text-white" : ""}>{isTrusted ? "Trusted" : "Not trusted"}</Badge>
                      {isTrusted ? (
                        <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={() => revokeMutation.mutate(ws.path)} disabled={revokeMutation.isPending}>Revoke</Button>
                      ) : (
                        <Button size="sm" variant="ghost" onClick={() => trustMutation.mutate(ws.path)} disabled={trustMutation.isPending}>Trust</Button>
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


function AgentsTab() {
  const { data: agents, isLoading } = useQuery<AgentProfile[]>({
    queryKey: ["/api/agents"],
  });

  if (isLoading) return <Skeleton className="h-40 w-full" />;

  return (
    <div className="space-y-4">
      {(!agents || agents.length === 0) ? (
        <Card>
          <CardContent className="p-6 text-center text-sm text-muted-foreground">
            No agent profiles registered.
          </CardContent>
        </Card>
      ) : (
        agents.map(agent => (
          <Card key={agent.name} data-testid={`agent-profile-${agent.name}`}>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <Sparkles className="w-4 h-4" />
                  {agent.name}
                </CardTitle>
                <div className="flex items-center gap-2">
                  <Badge variant="secondary" className="text-[10px]">v{agent.version}</Badge>
                  <Badge variant="outline" className="text-[10px]">{agent.risk_tier}</Badge>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">{agent.description}</p>
              <div>
                <span className="text-xs font-medium text-muted-foreground">Capabilities</span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {agent.capabilities.map(cap => (
                    <Badge key={cap} variant="secondary" className="text-[10px]">{cap}</Badge>
                  ))}
                </div>
              </div>
              <div className="flex items-center gap-4 text-xs text-muted-foreground">
                <span>Max autonomy: <span className="font-medium text-foreground">{agent.max_autonomy}</span></span>
              </div>
            </CardContent>
          </Card>
        ))
      )}
    </div>
  );
}

export default function SettingsPage() {
  const { data: settings, isLoading: settingsLoading } = useQuery<SettingsData>({ queryKey: ["/api/settings"] });
  const { data: orgData, isLoading: orgLoading } = useQuery<OrgSettingsData>({ queryKey: ORG_QUERY_KEY });

  if (settingsLoading || orgLoading) {
    return (
      <div className="space-y-6">
        <div><h1 className="text-xl font-semibold tracking-tight">Settings</h1><p className="text-sm text-muted-foreground mt-1">Loading configuration...</p></div>
        <Skeleton className="h-10 w-full" /><Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!settings || !orgData) return null;

  return (
    <div className="space-y-6">
      <div><h1 className="text-xl font-semibold tracking-tight">Settings</h1><p className="text-sm text-muted-foreground mt-1">Organization configuration and management</p></div>

      <Tabs defaultValue="general" className="space-y-4">
        <div className="overflow-x-auto">
          <TabsList className="inline-flex w-auto" data-testid="settings-tabs">
            <TabsTrigger value="general" data-testid="tab-general"><Server className="w-3.5 h-3.5 mr-1.5" />General</TabsTrigger>
            <TabsTrigger value="organization" data-testid="tab-organization"><Building2 className="w-3.5 h-3.5 mr-1.5" />Organization</TabsTrigger>
            <TabsTrigger value="rbac" data-testid="tab-rbac"><Shield className="w-3.5 h-3.5 mr-1.5" />RBAC</TabsTrigger>
            <TabsTrigger value="gbac" data-testid="tab-gbac"><Users className="w-3.5 h-3.5 mr-1.5" />GBAC</TabsTrigger>
            <TabsTrigger value="users" data-testid="tab-users"><UserCog className="w-3.5 h-3.5 mr-1.5" />Users</TabsTrigger>
            <TabsTrigger value="apikeys" data-testid="tab-apikeys"><KeyRound className="w-3.5 h-3.5 mr-1.5" />API Keys</TabsTrigger>
            <TabsTrigger value="security" data-testid="tab-security"><ShieldCheck className="w-3.5 h-3.5 mr-1.5" />Security</TabsTrigger>
            <TabsTrigger value="compliance" data-testid="tab-compliance"><FileCheck className="w-3.5 h-3.5 mr-1.5" />Compliance</TabsTrigger>
            <TabsTrigger value="notifications" data-testid="tab-notifications"><Bell className="w-3.5 h-3.5 mr-1.5" />Alerts</TabsTrigger>
            <TabsTrigger value="providers" data-testid="tab-providers"><Key className="w-3.5 h-3.5 mr-1.5" />Providers</TabsTrigger>
            <TabsTrigger value="workspaces" data-testid="tab-workspaces"><FolderCheck className="w-3.5 h-3.5 mr-1.5" />Workspaces</TabsTrigger>
            <TabsTrigger value="agents" data-testid="tab-agents"><Sparkles className="w-3.5 h-3.5 mr-1.5" />Agents</TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="general"><GeneralTab data={settings} /></TabsContent>
        <TabsContent value="organization"><OrgProfileTab org={orgData} /></TabsContent>
        <TabsContent value="rbac"><RbacTab org={orgData} /></TabsContent>
        <TabsContent value="gbac"><GbacTab org={orgData} /></TabsContent>
        <TabsContent value="users"><UsersTab org={orgData} /></TabsContent>
        <TabsContent value="apikeys"><ApiKeysTab org={orgData} /></TabsContent>
        <TabsContent value="security"><SecurityTab org={orgData} /></TabsContent>
        <TabsContent value="compliance"><ComplianceTab org={orgData} /></TabsContent>
        <TabsContent value="notifications"><NotificationsTab org={orgData} /></TabsContent>
        <TabsContent value="providers"><ProvidersTab /></TabsContent>
        <TabsContent value="workspaces"><WorkspacesTab /></TabsContent>
        <TabsContent value="agents"><AgentsTab /></TabsContent>
      </Tabs>
    </div>
  );
}
