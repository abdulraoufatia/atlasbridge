import { Link, useLocation } from "wouter";
import { useTheme } from "./theme-provider";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  LayoutDashboard, MonitorDot, MessageSquare, GitBranch,
  ShieldCheck, FileText, Settings, Sun, Moon, Menu, X, Plug, Terminal, FileCheck
} from "lucide-react";
import { useState } from "react";

const navItems = [
  { path: "/", label: "Overview", icon: LayoutDashboard },
  { path: "/sessions", label: "Sessions", icon: MonitorDot },
  { path: "/prompts", label: "Prompts", icon: MessageSquare },
  { path: "/traces", label: "Traces", icon: GitBranch },
  { path: "/integrity", label: "Integrity", icon: ShieldCheck },
  { path: "/audit", label: "Audit", icon: FileText },
  { path: "/repositories", label: "Repositories", icon: Plug },
  { path: "/evidence", label: "Evidence", icon: FileCheck },
  { path: "/terminal", label: "Terminal", icon: Terminal },
  { path: "/settings", label: "Settings", icon: Settings },
];

function HeaderBanner() {
  return (
    <div className="bg-[#0B2A3C] text-[#E6EEF5] text-xs font-mono flex items-center justify-center gap-6 py-1.5 px-4">
      <span className="flex items-center gap-1.5">
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        LOCAL ONLY
      </span>
      <span className="hidden sm:inline text-[#A8B3BD]" aria-hidden="true">|</span>
      <span className="hidden sm:inline text-[#A8B3BD] italic">Cloud observes, local executes</span>
    </div>
  );
}

function TopNav() {
  const [location] = useLocation();
  const { theme, toggleTheme } = useTheme();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <nav className="border-b bg-card" data-testid="nav-top">
      <div className="max-w-[1400px] mx-auto px-4">
        <div className="flex items-center justify-between gap-2 h-14">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 mr-4">
              <ShieldCheck className="w-5 h-5 text-primary" />
              <span className="font-semibold text-sm tracking-tight" data-testid="text-brand">
                AtlasBridge
              </span>
            </div>
            <div className="hidden md:flex items-center gap-1">
              {navItems.map(item => {
                const isActive = location === item.path ||
                  (item.path !== "/" && location.startsWith(item.path));
                return (
                  <Link key={item.path} href={item.path}>
                    <button
                      className={cn(
                        "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors",
                        isActive
                          ? "bg-primary text-primary-foreground"
                          : "text-muted-foreground"
                      )}
                      data-testid={`nav-${item.label.toLowerCase()}`}
                    >
                      <item.icon className="w-3.5 h-3.5" />
                      {item.label}
                    </button>
                  </Link>
                );
              })}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              size="icon"
              variant="ghost"
              onClick={toggleTheme}
              data-testid="button-theme-toggle"
              aria-label="Toggle theme"
            >
              {theme === "light" ? <Moon className="w-4 h-4" /> : <Sun className="w-4 h-4" />}
            </Button>
            <Button
              size="icon"
              variant="ghost"
              className="md:hidden"
              onClick={() => setMobileOpen(!mobileOpen)}
              data-testid="button-mobile-menu"
              aria-label="Toggle menu"
            >
              {mobileOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
            </Button>
          </div>
        </div>

        {mobileOpen && (
          <div className="md:hidden pb-3 flex flex-col gap-1" data-testid="nav-mobile-menu">
            {navItems.map(item => {
              const isActive = location === item.path ||
                (item.path !== "/" && location.startsWith(item.path));
              return (
                <Link key={item.path} href={item.path}>
                  <button
                    className={cn(
                      "flex items-center gap-2 w-full px-3 py-2 rounded-md text-sm transition-colors",
                      isActive
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground"
                    )}
                    onClick={() => setMobileOpen(false)}
                    data-testid={`nav-mobile-${item.label.toLowerCase()}`}
                  >
                    <item.icon className="w-4 h-4" />
                    {item.label}
                  </button>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </nav>
  );
}

export function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col min-h-screen bg-background">
      <HeaderBanner />
      <TopNav />
      <main className="flex-1 overflow-auto">
        <div className="max-w-[1400px] mx-auto px-4 py-6">
          {children}
        </div>
      </main>
    </div>
  );
}
