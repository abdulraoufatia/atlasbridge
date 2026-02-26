import { Switch, Route } from "wouter";
import { queryClient } from "./lib/queryClient";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/components/theme-provider";
import { Layout } from "@/components/layout";
import OverviewPage from "@/pages/overview";
import SessionsPage from "@/pages/sessions";
import SessionDetailPage from "@/pages/session-detail";
import PromptsPage from "@/pages/prompts";
import TracesPage from "@/pages/traces";
import IntegrityPage from "@/pages/integrity";
import AuditPage from "@/pages/audit";
import SettingsPage from "@/pages/settings";
import RepositoriesPage from "@/pages/repositories";
import TerminalPage from "@/pages/terminal";
import EvidencePage from "@/pages/evidence";
import NotFound from "@/pages/not-found";

function Router() {
  return (
    <Layout>
      <Switch>
        <Route path="/" component={OverviewPage} />
        <Route path="/sessions" component={SessionsPage} />
        <Route path="/sessions/:id" component={SessionDetailPage} />
        <Route path="/prompts" component={PromptsPage} />
        <Route path="/traces" component={TracesPage} />
        <Route path="/integrity" component={IntegrityPage} />
        <Route path="/audit" component={AuditPage} />
        <Route path="/settings" component={SettingsPage} />
        <Route path="/repositories" component={RepositoriesPage} />
        <Route path="/terminal" component={TerminalPage} />
        <Route path="/evidence" component={EvidencePage} />
        <Route component={NotFound} />
      </Switch>
    </Layout>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <TooltipProvider>
          <Toaster />
          <Router />
        </TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export default App;
