import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { PromptEntry, PromptType, PromptDecision } from "@shared/schema";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { decisionColor, formatTimestamp } from "@/lib/utils";
import { Search, ChevronLeft, ChevronRight } from "lucide-react";

const PAGE_SIZE = 10;

export default function PromptsPage() {
  const { data: prompts, isLoading } = useQuery<PromptEntry[]>({
    queryKey: ["/api/prompts"],
  });

  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [decisionFilter, setDecisionFilter] = useState<string>("all");
  const [page, setPage] = useState(0);

  const filtered = prompts?.filter(p => {
    if (search && !p.id.toLowerCase().includes(search.toLowerCase()) && !p.content.toLowerCase().includes(search.toLowerCase())) return false;
    if (typeFilter !== "all" && p.type !== typeFilter) return false;
    if (decisionFilter !== "all" && p.decision !== decisionFilter) return false;
    return true;
  }) || [];

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Prompts</h1>
        <p className="text-sm text-muted-foreground mt-1">Decision prompts and their outcomes</p>
      </div>

      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Search prompts..."
                value={search}
                onChange={e => { setSearch(e.target.value); setPage(0); }}
                className="pl-9"
                data-testid="input-prompt-search"
              />
            </div>
            <div className="flex gap-2 flex-wrap">
              <Select value={typeFilter} onValueChange={v => { setTypeFilter(v); setPage(0); }}>
                <SelectTrigger className="w-[150px]" data-testid="select-type-filter">
                  <SelectValue placeholder="Type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Types</SelectItem>
                  <SelectItem value="yes_no">Yes/No</SelectItem>
                  <SelectItem value="confirm_enter">Confirm</SelectItem>
                  <SelectItem value="numbered_choice">Choice</SelectItem>
                  <SelectItem value="free_text">Free Text</SelectItem>
                  <SelectItem value="multi_select">Multi Select</SelectItem>
                </SelectContent>
              </Select>
              <Select value={decisionFilter} onValueChange={v => { setDecisionFilter(v); setPage(0); }}>
                <SelectTrigger className="w-[140px]" data-testid="select-decision-filter">
                  <SelectValue placeholder="Decision" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Decisions</SelectItem>
                  <SelectItem value="auto">Auto</SelectItem>
                  <SelectItem value="human">Human</SelectItem>
                  <SelectItem value="escalated">Escalated</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {isLoading ? (
        <Card>
          <CardContent className="p-4 space-y-3">
            {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs">ID</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs">Content</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs hidden sm:table-cell">Type</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs hidden md:table-cell">Confidence</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs">Decision</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs hidden lg:table-cell">Action</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground text-xs hidden md:table-cell">Time</th>
                </tr>
              </thead>
              <tbody>
                {paginated.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">
                      No prompts match your filters
                    </td>
                  </tr>
                ) : (
                  paginated.map(prompt => (
                    <tr key={prompt.id} className="border-b last:border-0" data-testid={`row-prompt-${prompt.id}`}>
                      <td className="px-4 py-3 font-mono text-xs">{prompt.id}</td>
                      <td className="px-4 py-3 max-w-[250px] truncate">{prompt.content}</td>
                      <td className="px-4 py-3 hidden sm:table-cell">
                        <Badge variant="secondary" className="text-[10px]">{prompt.type.replace(/_/g, " ")}</Badge>
                      </td>
                      <td className="px-4 py-3 hidden md:table-cell">
                        <div className="flex items-center gap-2">
                          <div className="w-12 h-1.5 rounded-full bg-muted overflow-hidden">
                            <div
                              className={`h-full rounded-full ${prompt.confidence >= 0.7 ? "bg-emerald-500" : prompt.confidence >= 0.5 ? "bg-amber-500" : "bg-red-500"}`}
                              style={{ width: `${prompt.confidence * 100}%` }}
                            />
                          </div>
                          <span className="font-mono text-xs">{(prompt.confidence * 100).toFixed(0)}%</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant="secondary" className={`text-[10px] ${decisionColor(prompt.decision)}`}>
                          {prompt.decision}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 hidden lg:table-cell text-xs text-muted-foreground">
                        {prompt.actionTaken.replace(/_/g, " ")}
                      </td>
                      <td className="px-4 py-3 hidden md:table-cell text-xs text-muted-foreground">
                        {formatTimestamp(prompt.timestamp)}
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
                {filtered.length} result{filtered.length !== 1 ? "s" : ""}
              </span>
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  disabled={page === 0}
                  onClick={() => setPage(p => p - 1)}
                  data-testid="button-prev-page"
                >
                  <ChevronLeft className="w-4 h-4" />
                </Button>
                <span className="text-xs text-muted-foreground px-2">
                  {page + 1} / {totalPages}
                </span>
                <Button
                  variant="ghost"
                  size="icon"
                  disabled={page >= totalPages - 1}
                  onClick={() => setPage(p => p + 1)}
                  data-testid="button-next-page"
                >
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
