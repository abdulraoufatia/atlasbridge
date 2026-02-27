import { useState, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ShieldOff, Cpu } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { apiRequest } from "@/lib/queryClient";
import type { AutonomyMode } from "@shared/schema";

interface OperatorPanelProps {
  currentMode: AutonomyMode;
}

export function OperatorPanel({ currentMode }: OperatorPanelProps) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [displayMode, setDisplayMode] = useState(currentMode.toLowerCase());

  // Sync local state when server data changes (e.g. after query refetch)
  useEffect(() => {
    setDisplayMode(currentMode.toLowerCase());
  }, [currentMode]);

  const killSwitch = useMutation({
    mutationFn: () => apiRequest("POST", "/api/operator/kill-switch"),
    onSuccess: () => {
      setDisplayMode("off");
      toast({ title: "Kill switch activated", description: "Autopilot has been disabled." });
      queryClient.invalidateQueries({ queryKey: ["/api/overview"] });
    },
    onError: (err: Error) => {
      toast({ title: "Kill switch failed", description: err.message, variant: "destructive" });
    },
  });

  const setMode = useMutation({
    mutationFn: (mode: string) => apiRequest("POST", "/api/operator/mode", { mode }),
    onSuccess: (_data, mode) => {
      setDisplayMode(mode);
      toast({ title: "Mode updated", description: `Autonomy mode set to ${mode}.` });
      queryClient.invalidateQueries({ queryKey: ["/api/overview"] });
    },
    onError: (err: Error) => {
      setDisplayMode(currentMode.toLowerCase());
      toast({ title: "Mode change failed", description: err.message, variant: "destructive" });
    },
  });

  return (
    <Card data-testid="operator-panel">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Cpu className="w-4 h-4 text-primary" />
          Operator Controls
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-3">
            <div>
              <p className="text-xs text-muted-foreground mb-1">Autonomy Mode</p>
              <Select
                value={displayMode}
                onValueChange={(v) => setMode.mutate(v)}
                disabled={setMode.isPending}
              >
                <SelectTrigger className="w-32 h-8 text-xs" data-testid="select-autonomy-mode">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="off">Off</SelectItem>
                  <SelectItem value="assist">Assist</SelectItem>
                  <SelectItem value="full">Full</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                variant="destructive"
                size="sm"
                className="text-xs"
                disabled={killSwitch.isPending}
                data-testid="button-kill-switch"
              >
                <ShieldOff className="w-3.5 h-3.5 mr-1.5" />
                Kill Switch
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Disable Autopilot?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will immediately disable autonomous decision-making. All pending prompts will
                  require human approval until autopilot is re-enabled via the CLI or this panel.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => killSwitch.mutate()}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  data-testid="button-confirm-kill-switch"
                >
                  Disable Autopilot
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>

        {(killSwitch.isPending || setMode.isPending) && (
          <p className="text-[10px] text-muted-foreground animate-pulse">
            Executing command...
          </p>
        )}
      </CardContent>
    </Card>
  );
}
