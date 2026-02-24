import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "wouter";
import type { Session, RiskLevel, CIStatus } from "@shared/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { riskBg, statusColor, ciColor, formatTimestamp, timeAgo } from "@/lib/utils";
import { Search, ExternalLink } from "lucide-react";

export default function SessionsPage() {
  const { data: sessions, isLoading } = useQuery<Session[]>({
    queryKey: ["/api/sessions"],
  });

  const [search, setSearch] = useState("");
  const [riskFilter, setRiskFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [ciFilter, setCiFilter] = useState<string>("all");

  const filtered = sessions?.filter(s => {
    if (search && !s.id.toLowerCase().includes(search.toLowerCase()) && !s.tool.toLowerCase().includes(search.toLowerCase())) return false;
    if (riskFilter !== "all" && s.riskLevel !== riskFilter) return false;
    if (statusFilter !== "all" && s.status !== statusFilter) return false;
    if (ciFilter !== "all" && s.ciSnapshot !== ciFilter) return false;
    return true;
  }) || [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Sessions</h1>
        <p className="text-sm text-muted-foreground mt-1">Active and historical agent sessions</p>
      </div>

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
                  <SelectItem value="running">Running</SelectItem>
                  <SelectItem value="stopped">Stopped</SelectItem>
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
                        <Link href={`/sessions/${session.id}`}>
                          <button className="text-primary text-xs flex items-center gap-1" data-testid={`link-session-${session.id}`}>
                            View <ExternalLink className="w-3 h-3" />
                          </button>
                        </Link>
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
