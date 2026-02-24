import { spawn, type ChildProcess } from "child_process";
import type { WebSocket } from "ws";

interface TerminalSession {
  id: string;
  process: ChildProcess;
  ws: WebSocket;
}

const sessions = new Map<string, TerminalSession>();
let sessionCounter = 0;

export function handleTerminalConnection(ws: WebSocket) {
  ws.on("message", (rawMsg) => {
    try {
      const msg = JSON.parse(rawMsg.toString());

      switch (msg.type) {
        case "create": {
          sessionCounter++;
          const id = `term-${sessionCounter}`;
          const shell = process.env.SHELL || "/bin/bash";
          const proc = spawn(shell, ["-i"], {
            env: { ...process.env, TERM: "xterm-256color", COLORTERM: "truecolor" },
            cwd: process.env.HOME || "/home/runner",
            stdio: ["pipe", "pipe", "pipe"],
          });

          const session: TerminalSession = { id, process: proc, ws };
          sessions.set(id, session);

          proc.stdout?.on("data", (data: Buffer) => {
            if (ws.readyState === ws.OPEN) {
              ws.send(JSON.stringify({ type: "output", id, data: data.toString() }));
            }
          });

          proc.stderr?.on("data", (data: Buffer) => {
            if (ws.readyState === ws.OPEN) {
              ws.send(JSON.stringify({ type: "output", id, data: data.toString() }));
            }
          });

          proc.on("exit", (code) => {
            sessions.delete(id);
            if (ws.readyState === ws.OPEN) {
              ws.send(JSON.stringify({ type: "exit", id, code }));
            }
          });

          ws.send(JSON.stringify({ type: "created", id }));
          break;
        }

        case "input": {
          const session = sessions.get(msg.id);
          if (session && session.process.stdin) {
            session.process.stdin.write(msg.data);
          }
          break;
        }

        case "resize": {
          break;
        }

        case "close": {
          const session = sessions.get(msg.id);
          if (session) {
            session.process.kill();
            sessions.delete(msg.id);
          }
          break;
        }
      }
    } catch (e) {
      // ignore malformed messages
    }
  });

  ws.on("close", () => {
    const ids = Array.from(sessions.keys());
    for (const id of ids) {
      const session = sessions.get(id);
      if (session && session.ws === ws) {
        session.process.kill();
        sessions.delete(id);
      }
    }
  });
}
