import { useQuery } from "@tanstack/react-query";
import { useState, useMemo } from "react";
import type { TraceEntry } from "@shared/schema";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { riskBg, formatTimestamp } from "@/lib/utils";
import { ChevronLeft, ChevronRight, Link2 } from "lucide-react";

const PAGE_SIZE = 15;

export default function TracesPage() {
  const { data: traces, isLoading } = useQuery<TraceEntry[]>({
    queryKey: ["/api/traces"],
  });

  const [riskFilter, setRiskFilter] = useState<string>("all");
  const [page, setPage] = useState(0);

  const sorted = useMemo(() => {
    if (!traces) return [];
    let filtered = [...traces];
    if (riskFilter !== "all") {
      filtered = filtered.filter(t => t.riskLevel === riskFilter);
    }
    return filtered.sort((a, b) => {
      const timeDiff = new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
      if (timeDiff !== 0) return timeDiff;
      return b.id.localeCompare(a.id);
    });
  }, [traces, riskFilter]);

  const totalPages = Math.ceil(sorted.length / PAGE_SIZE);
  const paginated = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Traces</h1>
        <p className="text-sm text-muted-foreground mt-1">Decision trace entries with hash chain verification</p>
      </div>

      <Card>
        <CardContent className="p-4">
          <div className="flex items-center gap-3 flex-wrap">
            <Select value={riskFilter} onValueChange={v => { setRiskFilter(v); setPage(0); }}>
              <SelectTrigger className="w-[140px]" data-testid="select-trace-risk-filter">
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
            <span className="text-xs text-muted-foreground ml-auto">
              {sorted.length} trace{sorted.length !== 1 ? "s" : ""}
            </span>
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
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs w-10">#</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs">
                    <span className="flex items-center gap-1"><Link2 className="w-3 h-3" /> Hash</span>
                  </th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs">Risk</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs hidden sm:table-cell">Rule Matched</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs">Action</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs hidden md:table-cell">Session</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs hidden lg:table-cell">Time</th>
                </tr>
              </thead>
              <tbody>
                {paginated.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">
                      No traces match your filter
                    </td>
                  </tr>
                ) : (
                  paginated.map(trace => (
                    <tr key={trace.id} className="border-b last:border-0" data-testid={`row-trace-${trace.id}`}>
                      <td className="px-4 py-2.5 text-xs text-muted-foreground">{trace.stepIndex}</td>
                      <td className="px-4 py-2.5">
                        <code className="text-[11px] font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                          {trace.hash.slice(0, 20)}...
                        </code>
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge variant="secondary" className={`text-[10px] capitalize ${riskBg(trace.riskLevel)}`}>
                          {trace.riskLevel}
                        </Badge>
                      </td>
                      <td className="px-4 py-2.5 hidden sm:table-cell">
                        <span className="font-mono text-xs">{trace.ruleMatched}</span>
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={`text-xs font-medium ${
                          trace.action === "blocked" ? "text-red-600 dark:text-red-400" :
                          trace.action === "escalated" ? "text-orange-600 dark:text-orange-400" :
                          trace.action === "flagged" ? "text-amber-600 dark:text-amber-400" :
                          "text-emerald-600 dark:text-emerald-400"
                        }`}>
                          {trace.action}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 hidden md:table-cell">
                        <span className="font-mono text-xs text-muted-foreground">{trace.sessionId}</span>
                      </td>
                      <td className="px-4 py-2.5 hidden lg:table-cell text-xs text-muted-foreground">
                        {formatTimestamp(trace.timestamp)}
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
                Page {page + 1} of {totalPages}
              </span>
              <div className="flex items-center gap-1">
                <Button variant="ghost" size="icon" disabled={page === 0} onClick={() => setPage(p => p - 1)} data-testid="button-traces-prev">
                  <ChevronLeft className="w-4 h-4" />
                </Button>
                <Button variant="ghost" size="icon" disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)} data-testid="button-traces-next">
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
