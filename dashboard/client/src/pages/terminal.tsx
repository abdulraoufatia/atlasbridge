import { useState, useRef, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, X, Terminal as TerminalIcon, Maximize2, Minimize2 } from "lucide-react";

interface TerminalTab {
  id: string;
  name: string;
  buffer: string[];
  inputHistory: string[];
  historyIndex: number;
  currentInput: string;
}

function useTerminalWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const handlersRef = useRef<Map<string, (data: string) => void>>(new Map());
  const exitHandlersRef = useRef<Map<string, (code: number) => void>>(new Map());
  const createCallbackRef = useRef<((id: string) => void) | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/terminal`);

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "created" && createCallbackRef.current) {
          createCallbackRef.current(msg.id);
          createCallbackRef.current = null;
        } else if (msg.type === "output") {
          const handler = handlersRef.current.get(msg.id);
          if (handler) handler(msg.data);
        } else if (msg.type === "exit") {
          const handler = exitHandlersRef.current.get(msg.id);
          if (handler) handler(msg.code);
        }
      } catch {}
    };

    ws.onclose = () => {
      setTimeout(connect, 2000);
    };

    wsRef.current = ws;
  }, []);

  const createTerminal = useCallback((onCreated: (id: string) => void) => {
    createCallbackRef.current = onCreated;
    wsRef.current?.send(JSON.stringify({ type: "create" }));
  }, []);

  const sendInput = useCallback((id: string, data: string) => {
    wsRef.current?.send(JSON.stringify({ type: "input", id, data }));
  }, []);

  const closeTerminal = useCallback((id: string) => {
    wsRef.current?.send(JSON.stringify({ type: "close", id }));
  }, []);

  const onOutput = useCallback((id: string, handler: (data: string) => void) => {
    handlersRef.current.set(id, handler);
  }, []);

  const onExit = useCallback((id: string, handler: (code: number) => void) => {
    exitHandlersRef.current.set(id, handler);
  }, []);

  return { connect, createTerminal, sendInput, closeTerminal, onOutput, onExit };
}

function TerminalView({ tab, sendInput, fontSize }: { tab: TerminalTab; sendInput: (data: string) => void; fontSize: number }) {
  const outputRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [tab.buffer]);

  useEffect(() => {
    inputRef.current?.focus();
  }, [tab.id]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      const val = (e.target as HTMLInputElement).value;
      sendInput(val + "\n");
      (e.target as HTMLInputElement).value = "";
    } else if (e.key === "c" && e.ctrlKey) {
      sendInput("\x03");
    } else if (e.key === "d" && e.ctrlKey) {
      sendInput("\x04");
    }
  };

  return (
    <div
      className="flex flex-col h-full bg-black text-green-400 font-mono rounded-b-md overflow-hidden"
      onClick={() => inputRef.current?.focus()}
    >
      <div
        ref={outputRef}
        className="flex-1 overflow-auto p-3 whitespace-pre-wrap break-all"
        style={{ fontSize: `${fontSize}px`, lineHeight: "1.4" }}
      >
        {tab.buffer.map((line, i) => (
          <div key={i}>{line || "\u00A0"}</div>
        ))}
      </div>
      <div className="flex items-center border-t border-gray-800 px-3 py-1">
        <span className="text-green-500 mr-2" style={{ fontSize: `${fontSize}px` }}>$</span>
        <input
          ref={inputRef}
          type="text"
          className="flex-1 bg-transparent text-green-400 outline-none border-none"
          style={{ fontSize: `${fontSize}px` }}
          onKeyDown={handleKeyDown}
          autoComplete="off"
          spellCheck={false}
          data-testid="input-terminal"
        />
      </div>
    </div>
  );
}

export default function TerminalPage() {
  const [tabs, setTabs] = useState<TerminalTab[]>([]);
  const [activeTab, setActiveTab] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [fontSize, setFontSize] = useState(13);
  const ws = useTerminalWebSocket();

  useEffect(() => {
    ws.connect();
  }, [ws.connect]);

  const createNewTab = useCallback(() => {
    ws.createTerminal((id) => {
      const newTab: TerminalTab = {
        id,
        name: `Terminal ${tabs.length + 1}`,
        buffer: [`Connected to terminal session ${id}`, ""],
        inputHistory: [],
        historyIndex: -1,
        currentInput: "",
      };

      ws.onOutput(id, (data) => {
        setTabs(prev => prev.map(t => {
          if (t.id !== id) return t;
          const lines = data.split("\n");
          const newBuffer = [...t.buffer];
          if (newBuffer.length > 0 && lines.length > 0) {
            newBuffer[newBuffer.length - 1] += lines[0];
            for (let i = 1; i < lines.length; i++) {
              newBuffer.push(lines[i]);
            }
          }
          if (newBuffer.length > 1000) {
            newBuffer.splice(0, newBuffer.length - 1000);
          }
          return { ...t, buffer: newBuffer };
        }));
      });

      ws.onExit(id, (code) => {
        setTabs(prev => prev.map(t =>
          t.id === id ? { ...t, buffer: [...t.buffer, `\nProcess exited with code ${code}`, ""] } : t
        ));
      });

      setTabs(prev => [...prev, newTab]);
      setActiveTab(id);
    });
  }, [ws, tabs.length]);

  const closeTab = useCallback((id: string) => {
    ws.closeTerminal(id);
    setTabs(prev => {
      const updated = prev.filter(t => t.id !== id);
      if (activeTab === id) {
        setActiveTab(updated.length > 0 ? updated[updated.length - 1].id : null);
      }
      return updated;
    });
  }, [ws, activeTab]);

  const sendInput = useCallback((data: string) => {
    if (activeTab) {
      ws.sendInput(activeTab, data);
    }
  }, [ws, activeTab]);

  const activeTerminal = tabs.find(t => t.id === activeTab);

  const containerClass = isFullscreen
    ? "fixed inset-0 z-50 bg-background p-4"
    : "space-y-4";

  return (
    <div className={containerClass}>
      {!isFullscreen && (
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Terminal</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Run commands and manage multiple terminal instances
          </p>
        </div>
      )}

      <Card className={`${isFullscreen ? "h-full" : "min-h-[500px]"} flex flex-col`}>
        <div className="flex items-center justify-between border-b px-2 py-1 gap-2">
          <div className="flex items-center gap-1 overflow-x-auto flex-1">
            {tabs.map(tab => (
              <div
                key={tab.id}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-t-md text-xs cursor-pointer shrink-0 ${
                  tab.id === activeTab
                    ? "bg-black text-green-400"
                    : "bg-muted text-muted-foreground hover:bg-muted/80"
                }`}
                onClick={() => setActiveTab(tab.id)}
                data-testid={`tab-terminal-${tab.id}`}
              >
                <TerminalIcon className="w-3 h-3" />
                <span>{tab.name}</span>
                <button
                  onClick={(e) => { e.stopPropagation(); closeTab(tab.id); }}
                  className="ml-1 hover:text-red-400 transition-colors"
                  data-testid={`button-close-terminal-${tab.id}`}
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            ))}
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2"
              onClick={createNewTab}
              data-testid="button-new-terminal"
            >
              <Plus className="w-3.5 h-3.5 mr-1" />
              New
            </Button>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <Select value={String(fontSize)} onValueChange={(v) => setFontSize(Number(v))}>
              <SelectTrigger className="h-7 w-[70px] text-xs" data-testid="select-font-size">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="11">11px</SelectItem>
                <SelectItem value="13">13px</SelectItem>
                <SelectItem value="15">15px</SelectItem>
                <SelectItem value="17">17px</SelectItem>
              </SelectContent>
            </Select>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2"
              onClick={() => setIsFullscreen(!isFullscreen)}
              data-testid="button-toggle-fullscreen"
            >
              {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
            </Button>
          </div>
        </div>

        <CardContent className="flex-1 p-0">
          {activeTerminal ? (
            <TerminalView
              tab={activeTerminal}
              sendInput={sendInput}
              fontSize={fontSize}
            />
          ) : (
            <div className="flex flex-col items-center justify-center h-full min-h-[400px] text-muted-foreground gap-4">
              <TerminalIcon className="w-12 h-12 opacity-30" />
              <div className="text-center">
                <p className="text-sm font-medium">No terminals open</p>
                <p className="text-xs mt-1">Click "New" to open a terminal session</p>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={createNewTab}
                data-testid="button-new-terminal-empty"
              >
                <Plus className="w-3.5 h-3.5 mr-1.5" />
                Open Terminal
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
