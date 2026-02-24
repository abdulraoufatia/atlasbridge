import { useQuery } from "@tanstack/react-query";
import { useParams, Link } from "wouter";
import type { SessionDetail } from "@shared/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { riskBg, statusColor, decisionColor, formatTimestamp, timeAgo, sanitizeText } from "@/lib/utils";
import { ArrowLeft, Info, ChevronDown, Code } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useState } from "react";

export default function SessionDetailPage() {
  const params = useParams<{ id: string }>();
  const [rawOpen, setRawOpen] = useState(false);

  const { data, isLoading, error } = useQuery<SessionDetail>({
    queryKey: ["/api/sessions", params.id],
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="space-y-4">
        <Link href="/sessions">
          <Button variant="ghost" size="sm" data-testid="button-back-sessions">
            <ArrowLeft className="w-4 h-4 mr-1" /> Back to Sessions
          </Button>
        </Link>
        <Card>
          <CardContent className="p-8 text-center text-muted-foreground">
            Session not found
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 flex-wrap">
        <Link href="/sessions">
          <Button variant="ghost" size="sm" data-testid="button-back-sessions">
            <ArrowLeft className="w-4 h-4 mr-1" /> Sessions
          </Button>
        </Link>
        <span className="text-muted-foreground">/</span>
        <h1 className="text-lg font-semibold font-mono" data-testid="text-session-id">{data.id}</h1>
        <Badge variant="secondary" className={statusColor(data.status)}>{data.status}</Badge>
        <Badge variant="secondary" className={`capitalize ${riskBg(data.riskLevel)}`}>{data.riskLevel}</Badge>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Session Metadata</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="space-y-2 text-sm">
              {Object.entries(data.metadata).map(([key, val]) => (
                <div key={key} className="flex justify-between gap-4">
                  <dt className="text-muted-foreground shrink-0">{key}</dt>
                  <dd className="text-right font-mono text-xs truncate">{sanitizeText(val)}</dd>
                </div>
              ))}
              <div className="flex justify-between gap-4 pt-2 border-t">
                <dt className="text-muted-foreground">Started</dt>
                <dd className="text-right text-xs">{formatTimestamp(data.startTime)}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">Last Activity</dt>
                <dd className="text-right text-xs">{timeAgo(data.lastActivity)}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">Escalations</dt>
                <dd className="text-right text-xs font-medium">
                  {data.escalationsCount > 0 ? (
                    <span className="text-orange-600 dark:text-orange-400">{data.escalationsCount}</span>
                  ) : "0"}
                </dd>
              </div>
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Info className="w-4 h-4 text-primary" />
              Explain
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground leading-relaxed" data-testid="text-explain">
              {data.explainPanel}
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">Prompts ({data.prompts.length})</CardTitle>
        </CardHeader>
        {data.prompts.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="px-4 py-2 font-medium text-muted-foreground text-xs">ID</th>
                  <th className="px-4 py-2 font-medium text-muted-foreground text-xs">Content</th>
                  <th className="px-4 py-2 font-medium text-muted-foreground text-xs hidden sm:table-cell">Type</th>
                  <th className="px-4 py-2 font-medium text-muted-foreground text-xs hidden md:table-cell">Confidence</th>
                  <th className="px-4 py-2 font-medium text-muted-foreground text-xs">Decision</th>
                </tr>
              </thead>
              <tbody>
                {data.prompts.map(p => (
                  <tr key={p.id} className="border-b last:border-0" data-testid={`row-prompt-${p.id}`}>
                    <td className="px-4 py-2 font-mono text-xs">{p.id}</td>
                    <td className="px-4 py-2 max-w-[200px] truncate">{p.content}</td>
                    <td className="px-4 py-2 hidden sm:table-cell">
                      <Badge variant="secondary" className="text-[10px]">{p.type}</Badge>
                    </td>
                    <td className="px-4 py-2 hidden md:table-cell">
                      <span className={`font-mono text-xs ${p.confidence < 0.5 ? "text-orange-600 dark:text-orange-400" : ""}`}>
                        {(p.confidence * 100).toFixed(0)}%
                      </span>
                    </td>
                    <td className="px-4 py-2">
                      <Badge variant="secondary" className={`text-[10px] ${decisionColor(p.decision)}`}>
                        {p.decision}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <CardContent>
            <p className="text-sm text-muted-foreground">No prompts in this session</p>
          </CardContent>
        )}
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">Decision Trace ({data.decisionTrace.length})</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="max-h-[300px] overflow-auto">
            {data.decisionTrace.map((trace, i) => (
              <div key={trace.id} className={`flex items-center gap-3 px-4 py-2.5 ${i < data.decisionTrace.length - 1 ? "border-b" : ""}`}>
                <span className="text-xs text-muted-foreground w-6 text-right shrink-0">
                  #{trace.stepIndex}
                </span>
                <Badge variant="secondary" className={`text-[10px] capitalize ${riskBg(trace.riskLevel)}`}>
                  {trace.riskLevel}
                </Badge>
                <span className="text-xs font-mono text-muted-foreground truncate">{trace.ruleMatched}</span>
                <span className="text-xs ml-auto shrink-0">{trace.action}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Collapsible open={rawOpen} onOpenChange={setRawOpen}>
        <Card>
          <CollapsibleTrigger asChild>
            <CardHeader className="pb-3 cursor-pointer">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Code className="w-4 h-4" />
                Raw View (Sanitized)
                <ChevronDown className={`w-4 h-4 ml-auto transition-transform ${rawOpen ? "rotate-180" : ""}`} />
              </CardTitle>
            </CardHeader>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <CardContent className="pt-0">
              <pre className="bg-muted rounded-md p-4 text-xs font-mono overflow-x-auto whitespace-pre-wrap" data-testid="text-raw-view">
                {sanitizeText(data.rawView)}
              </pre>
            </CardContent>
          </CollapsibleContent>
        </Card>
      </Collapsible>
    </div>
  );
}
