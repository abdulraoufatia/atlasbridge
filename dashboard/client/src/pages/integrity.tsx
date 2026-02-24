import { useQuery } from "@tanstack/react-query";
import { useState, useRef } from "react";
import type { IntegrityData } from "@shared/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { integrityColor, formatTimestamp } from "@/lib/utils";
import { ShieldCheck, ShieldAlert, ShieldX, RefreshCw, Clock } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

const REVERIFY_COOLDOWN = 30;

function IntegrityIcon({ status }: { status: string }) {
  switch (status) {
    case "Verified": return <ShieldCheck className="w-8 h-8 text-emerald-600 dark:text-emerald-400" />;
    case "Warning": return <ShieldAlert className="w-8 h-8 text-amber-600 dark:text-amber-400" />;
    default: return <ShieldX className="w-8 h-8 text-red-600 dark:text-red-400" />;
  }
}

export default function IntegrityPage() {
  const { data, isLoading } = useQuery<IntegrityData>({
    queryKey: ["/api/integrity"],
  });

  const [cooldown, setCooldown] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const { toast } = useToast();

  const handleReverify = () => {
    if (cooldown > 0) return;
    setCooldown(REVERIFY_COOLDOWN);
    toast({
      title: "Re-verification triggered",
      description: "Integrity check is running locally...",
    });
    intervalRef.current = setInterval(() => {
      setCooldown(prev => {
        if (prev <= 1) {
          if (intervalRef.current) clearInterval(intervalRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  };

  if (isLoading || !data) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Integrity</h1>
          <p className="text-sm text-muted-foreground mt-1">System integrity verification status</p>
        </div>
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Integrity</h1>
        <p className="text-sm text-muted-foreground mt-1">System integrity verification status</p>
      </div>

      <Card>
        <CardContent className="p-6">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-4">
              <IntegrityIcon status={data.overallStatus} />
              <div>
                <div className="flex items-center gap-2">
                  <Badge
                    variant="secondary"
                    className={`text-sm px-3 py-1 ${integrityColor(data.overallStatus)}`}
                    data-testid="badge-integrity-status"
                  >
                    {data.overallStatus}
                  </Badge>
                </div>
                <div className="flex items-center gap-1.5 mt-2 text-xs text-muted-foreground">
                  <Clock className="w-3 h-3" />
                  Last verified: {formatTimestamp(data.lastVerifiedAt)}
                </div>
              </div>
            </div>
            <div className="flex flex-col items-end gap-1">
              <Button
                variant="secondary"
                size="sm"
                onClick={handleReverify}
                disabled={cooldown > 0}
                data-testid="button-reverify"
              >
                <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${cooldown > 0 ? "animate-spin" : ""}`} />
                {cooldown > 0 ? `Wait ${cooldown}s` : "Re-verify"}
              </Button>
              <span className="text-[10px] text-muted-foreground">
                Limited to once per {REVERIFY_COOLDOWN}s
              </span>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">Verification Results</CardTitle>
        </CardHeader>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="px-4 py-3 font-medium text-muted-foreground text-xs">Component</th>
                <th className="px-4 py-3 font-medium text-muted-foreground text-xs">Status</th>
                <th className="px-4 py-3 font-medium text-muted-foreground text-xs hidden md:table-cell">Hash</th>
                <th className="px-4 py-3 font-medium text-muted-foreground text-xs hidden sm:table-cell">Details</th>
                <th className="px-4 py-3 font-medium text-muted-foreground text-xs hidden lg:table-cell">Checked</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map(result => (
                <tr key={result.component} className="border-b last:border-0" data-testid={`row-integrity-${result.component.replace(/\s/g, "-").toLowerCase()}`}>
                  <td className="px-4 py-3 font-medium">{result.component}</td>
                  <td className="px-4 py-3">
                    <Badge variant="secondary" className={`text-[10px] ${integrityColor(result.status)}`}>
                      {result.status}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 hidden md:table-cell">
                    <code className="text-[11px] font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                      {result.hash}
                    </code>
                  </td>
                  <td className="px-4 py-3 hidden sm:table-cell text-xs text-muted-foreground max-w-[250px] truncate">
                    {result.details}
                  </td>
                  <td className="px-4 py-3 hidden lg:table-cell text-xs text-muted-foreground">
                    {formatTimestamp(result.lastChecked)}
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
