import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { apiRequest } from "@/lib/queryClient";
import { Key, CheckCircle, XCircle, AlertCircle, Trash2 } from "lucide-react";

interface ProviderConfig {
  provider: string;
  status: "configured" | "validated" | "invalid";
  key_prefix: string | null;
  configured_at: string | null;
  validated_at: string | null;
  last_error: string | null;
}

const QUERY_KEY = ["/api/providers"];
const SUPPORTED_PROVIDERS = ["openai", "anthropic", "gemini"] as const;
type SupportedProvider = typeof SUPPORTED_PROVIDERS[number];

const PROVIDER_INFO: Record<SupportedProvider, { label: string; keyHint: string }> = {
  openai: { label: "OpenAI", keyHint: "sk-…" },
  anthropic: { label: "Anthropic", keyHint: "sk-ant-…" },
  gemini: { label: "Google Gemini", keyHint: "AIza…" },
};

function StatusBadge({ status }: { status: string }) {
  if (status === "validated") {
    return (
      <Badge className="bg-emerald-600 text-white gap-1" data-testid="badge-validated">
        <CheckCircle className="w-3 h-3" /> Validated
      </Badge>
    );
  }
  if (status === "configured") {
    return (
      <Badge variant="secondary" className="gap-1" data-testid="badge-configured">
        <AlertCircle className="w-3 h-3" /> Configured
      </Badge>
    );
  }
  return (
    <Badge variant="destructive" className="gap-1" data-testid="badge-invalid">
      <XCircle className="w-3 h-3" /> Invalid
    </Badge>
  );
}

function ProviderCard({
  provider,
  config,
}: {
  provider: SupportedProvider;
  config: ProviderConfig | undefined;
}) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const info = PROVIDER_INFO[provider];

  const [keyValue, setKeyValue] = useState("");
  const [showInput, setShowInput] = useState(false);

  const saveMutation = useMutation({
    mutationFn: (key: string) =>
      apiRequest("POST", "/api/providers", { provider, key }),
    onSuccess: () => {
      toast({ title: "Key saved", description: `${info.label} key stored securely.` });
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
      setKeyValue("");
      setShowInput(false);
    },
    onError: (e: Error) =>
      toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const validateMutation = useMutation({
    mutationFn: () => apiRequest("POST", `/api/providers/${provider}/validate`),
    onSuccess: () => {
      toast({ title: "Validated", description: `${info.label} key is valid.` });
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
    onError: (e: Error) =>
      toast({ title: "Validation failed", description: e.message, variant: "destructive" }),
  });

  const removeMutation = useMutation({
    mutationFn: () => apiRequest("DELETE", `/api/providers/${provider}`),
    onSuccess: () => {
      toast({ title: "Removed", description: `${info.label} key removed.` });
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
    onError: (e: Error) =>
      toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const isConfigured = Boolean(config);

  return (
    <Card data-testid={`card-provider-${provider}`}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            <Key className="w-4 h-4 text-muted-foreground" />
            {info.label}
          </CardTitle>
          {config && <StatusBadge status={config.status} />}
        </div>
        {config?.key_prefix && (
          <CardDescription className="font-mono text-xs mt-1">
            Key: {config.key_prefix}
          </CardDescription>
        )}
        {config?.last_error && config.status === "invalid" && (
          <CardDescription className="text-destructive text-xs mt-1">
            {config.last_error}
          </CardDescription>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {showInput ? (
          <div className="space-y-2">
            <Label htmlFor={`key-${provider}`} className="text-xs text-muted-foreground">
              API key — stored securely, never displayed again
            </Label>
            <Input
              id={`key-${provider}`}
              type="password"
              placeholder={info.keyHint}
              value={keyValue}
              onChange={e => setKeyValue(e.target.value)}
              onKeyDown={e => e.key === "Enter" && keyValue && saveMutation.mutate(keyValue)}
              data-testid={`input-key-${provider}`}
              className="font-mono text-sm"
            />
            <p className="text-[11px] text-muted-foreground">
              API usage is billed by your provider. AtlasBridge does not charge for API access.
            </p>
            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={() => keyValue && saveMutation.mutate(keyValue)}
                disabled={!keyValue || saveMutation.isPending}
                data-testid={`button-save-${provider}`}
              >
                {saveMutation.isPending ? "Saving…" : "Save"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => { setShowInput(false); setKeyValue(""); }}
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant={isConfigured ? "outline" : "default"}
              onClick={() => setShowInput(true)}
              data-testid={`button-add-key-${provider}`}
            >
              {isConfigured ? "Replace key" : "Add key"}
            </Button>
            {isConfigured && (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => validateMutation.mutate()}
                  disabled={validateMutation.isPending}
                  data-testid={`button-validate-${provider}`}
                >
                  {validateMutation.isPending ? "Validating…" : "Validate"}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-destructive hover:text-destructive"
                  onClick={() => removeMutation.mutate()}
                  disabled={removeMutation.isPending}
                  data-testid={`button-remove-${provider}`}
                >
                  <Trash2 className="w-3.5 h-3.5 mr-1" />
                  Remove
                </Button>
              </>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function ProvidersPage() {
  const { data: providers, isLoading } = useQuery<ProviderConfig[]>({
    queryKey: QUERY_KEY,
    refetchInterval: 15_000,
  });

  const configMap = Object.fromEntries(
    (providers ?? []).map(p => [p.provider, p]),
  ) as Record<string, ProviderConfig>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Providers</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Manage AI provider API keys. Keys are stored in your OS keychain and never
          exposed after saving.
        </p>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {SUPPORTED_PROVIDERS.map(p => (
            <Skeleton key={p} className="h-40 w-full" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {SUPPORTED_PROVIDERS.map(provider => (
            <ProviderCard
              key={provider}
              provider={provider}
              config={configMap[provider]}
            />
          ))}
        </div>
      )}

      <Card className="border-dashed">
        <CardContent className="p-4">
          <p className="text-xs text-muted-foreground">
            <strong>Storage:</strong> API keys are stored in your OS keychain (macOS Keychain,
            Linux Secret Service). Only a short prefix is shown for identification. Keys are
            never transmitted to AtlasBridge servers and never appear in logs or audit traces.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
