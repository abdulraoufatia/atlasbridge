import { useQuery } from "@tanstack/react-query";
import { useState, useMemo } from "react";
import type { AuditEntry } from "@shared/schema";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { riskBg, formatTimestamp } from "@/lib/utils";
import { Search, Download, ChevronLeft, ChevronRight, CheckCircle, XCircle } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

const PAGE_SIZE = 15;

export default function AuditPage() {
  const { data: audit, isLoading } = useQuery<AuditEntry[]>({
    queryKey: ["/api/audit"],
  });

  const [search, setSearch] = useState("");
  const [riskFilter, setRiskFilter] = useState<string>("all");
  const [page, setPage] = useState(0);
  const { toast } = useToast();

  const filtered = useMemo(() => {
    if (!audit) return [];
    return audit.filter(a => {
      if (search && !a.message.toLowerCase().includes(search.toLowerCase()) &&
        !a.sessionId.toLowerCase().includes(search.toLowerCase()) &&
        !a.id.toLowerCase().includes(search.toLowerCase())) return false;
      if (riskFilter !== "all" && a.riskLevel !== riskFilter) return false;
      return true;
    });
  }, [audit, search, riskFilter]);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const exportData = (format: "json" | "csv") => {
    if (!filtered.length) return;
    let content: string;
    let mimeType: string;
    let ext: string;

    if (format === "json") {
      content = JSON.stringify(filtered, null, 2);
      mimeType = "application/json";
      ext = "json";
    } else {
      const headers = ["id", "timestamp", "riskLevel", "sessionId", "promptType", "actionTaken", "message", "hashVerified"];
      const rows = filtered.map(a => headers.map(h => `"${String(a[h as keyof AuditEntry]).replace(/"/g, '""')}"`).join(","));
      content = [headers.join(","), ...rows].join("\n");
      mimeType = "text/csv";
      ext = "csv";
    }

    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `atlasbridge-audit.${ext}`;
    link.click();
    URL.revokeObjectURL(url);
    toast({ title: `Exported ${filtered.length} entries as ${ext.toUpperCase()}` });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Audit</h1>
          <p className="text-sm text-muted-foreground mt-1">Searchable audit log with hash verification</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={() => exportData("json")} data-testid="button-export-json">
            <Download className="w-3.5 h-3.5 mr-1.5" /> JSON
          </Button>
          <Button variant="secondary" size="sm" onClick={() => exportData("csv")} data-testid="button-export-csv">
            <Download className="w-3.5 h-3.5 mr-1.5" /> CSV
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Search audit entries..."
                value={search}
                onChange={e => { setSearch(e.target.value); setPage(0); }}
                className="pl-9"
                data-testid="input-audit-search"
              />
            </div>
            <Select value={riskFilter} onValueChange={v => { setRiskFilter(v); setPage(0); }}>
              <SelectTrigger className="w-[140px]" data-testid="select-audit-risk">
                <SelectValue placeholder="Risk" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Risks</SelectItem>
                <SelectItem value="low">Low</SelectItem>
                <SelectItem value="medium">Medium</SelectItem>
                <SelectItem value="high">High</SelectItem>
                <SelectItem value="critical">Critical</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {isLoading ? (
        <Card>
          <CardContent className="p-4 space-y-3">
            {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs">ID</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs">Message</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs">Risk</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs hidden sm:table-cell">Session</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs hidden md:table-cell">Action</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs hidden lg:table-cell">Hash</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs hidden lg:table-cell">Time</th>
                </tr>
              </thead>
              <tbody>
                {paginated.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">
                      No audit entries match your search
                    </td>
                  </tr>
                ) : (
                  paginated.map(entry => (
                    <tr key={entry.id} className="border-b last:border-0" data-testid={`row-audit-${entry.id}`}>
                      <td className="px-4 py-2.5 font-mono text-xs">{entry.id}</td>
                      <td className="px-4 py-2.5 max-w-[250px] truncate">{entry.message}</td>
                      <td className="px-4 py-2.5">
                        <Badge variant="secondary" className={`text-[10px] capitalize ${riskBg(entry.riskLevel)}`}>
                          {entry.riskLevel}
                        </Badge>
                      </td>
                      <td className="px-4 py-2.5 hidden sm:table-cell font-mono text-xs text-muted-foreground">
                        {entry.sessionId}
                      </td>
                      <td className="px-4 py-2.5 hidden md:table-cell text-xs text-muted-foreground">
                        {entry.actionTaken.replace(/_/g, " ")}
                      </td>
                      <td className="px-4 py-2.5 hidden lg:table-cell">
                        {entry.hashVerified ? (
                          <CheckCircle className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                        ) : (
                          <XCircle className="w-3.5 h-3.5 text-red-600 dark:text-red-400" />
                        )}
                      </td>
                      <td className="px-4 py-2.5 hidden lg:table-cell text-xs text-muted-foreground">
                        {formatTimestamp(entry.timestamp)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          {totalPages > 1 && (
            <div className="flex items-center justify-between gap-2 px-4 py-3 border-t">
              <span className="text-xs text-muted-foreground">
                {filtered.length} entr{filtered.length !== 1 ? "ies" : "y"}
              </span>
              <div className="flex items-center gap-1">
                <Button variant="ghost" size="icon" disabled={page === 0} onClick={() => setPage(p => p - 1)} data-testid="button-audit-prev">
                  <ChevronLeft className="w-4 h-4" />
                </Button>
                <span className="text-xs text-muted-foreground px-2">{page + 1} / {totalPages}</span>
                <Button variant="ghost" size="icon" disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)} data-testid="button-audit-next">
                  <ChevronRight className="w-4 h-4" />
                </Button>
              </div>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
