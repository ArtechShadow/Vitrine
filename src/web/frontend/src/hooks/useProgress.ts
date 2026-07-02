// Live progress for a scene/job.
//
// The canonical channel is Server-Sent Events on /stream/<id> (already served
// by app.py). We consume it with EventSource and only fall back to polling
// /api/scenes/<id>/progress when the stream errors before completion — the PR's
// 1.5–2.5s polling loop is the fallback, never the primary path.

import { useEffect, useReducer, useRef } from "react";
import { API_BASE } from "../api/http";

export interface LiveProgress {
  /** Latest job state (queued | running | stage_* | completed | failed | ...). */
  status: string;
  /** Bare current stage key, if known. */
  stage: string;
  /** 0..100. */
  percent: number;
  message: string;
  logs: string[];
  /** stage → preview path, mirrored from the stream's `previews` events. */
  previews: Record<string, string>;
  done: boolean;
  error: string | null;
  /** How progress is currently arriving. */
  transport: "connecting" | "sse" | "poll" | "done";
}

type Action =
  | { type: "state"; status: string; stage: string }
  | { type: "progress"; percent: number }
  | { type: "log"; line: string }
  | { type: "previews"; previews: Record<string, string> }
  | { type: "message"; message: string }
  | { type: "transport"; transport: LiveProgress["transport"] }
  | { type: "done"; status: string; error: string | null }
  | { type: "reset" };

const INITIAL: LiveProgress = {
  status: "",
  stage: "",
  percent: 0,
  message: "",
  logs: [],
  previews: {},
  done: false,
  error: null,
  transport: "connecting",
};

const MAX_LOGS = 500;

function reducer(state: LiveProgress, action: Action): LiveProgress {
  switch (action.type) {
    case "state":
      return { ...state, status: action.status, stage: action.stage || state.stage };
    case "progress":
      return { ...state, percent: Math.max(0, Math.min(100, action.percent)) };
    case "message":
      return { ...state, message: action.message };
    case "log": {
      const logs = state.logs.length >= MAX_LOGS ? state.logs.slice(-(MAX_LOGS - 1)) : state.logs.slice();
      logs.push(action.line);
      return { ...state, logs, message: action.line };
    }
    case "previews":
      return { ...state, previews: { ...state.previews, ...action.previews } };
    case "transport":
      return { ...state, transport: action.transport };
    case "done":
      return {
        ...state,
        status: action.status,
        done: true,
        error: action.error,
        percent: action.error ? state.percent : 100,
        transport: "done",
      };
    case "reset":
      return { ...INITIAL };
    default:
      return state;
  }
}

function bareStage(status: string, currentStage?: string): string {
  if (status.startsWith("stage_")) return status.replace(/^stage_/, "");
  return currentStage ?? "";
}

/**
 * @param sceneId  scene/job id to follow (null disables).
 * @param active   whether to keep a live connection open. Pass false once the
 *                 scene is terminal to release the stream.
 */
export function useProgress(sceneId: string | null, active: boolean): LiveProgress {
  const [state, dispatch] = useReducer(reducer, INITIAL);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    dispatch({ type: "reset" });
    if (!sceneId || !active) return;

    let closed = false;
    let es: EventSource | null = null;

    const stopPoll = () => {
      if (pollRef.current != null) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };

    // ---- Fallback: poll the synthesized progress endpoint. ----
    const startPolling = () => {
      if (closed || pollRef.current != null) return;
      dispatch({ type: "transport", transport: "poll" });
      const tick = async () => {
        try {
          const res = await fetch(`${API_BASE}/api/scenes/${encodeURIComponent(sceneId)}/progress`);
          if (!res.ok) return;
          const p = (await res.json()) as {
            status?: string;
            state?: string;
            stage?: string;
            current_stage?: string;
            percent?: number;
            progress?: number;
            message?: string;
            error?: string | null;
          };
          const status = p.status ?? p.state ?? "";
          const stage = p.stage ?? bareStage(status, p.current_stage);
          if (status) dispatch({ type: "state", status, stage });
          const percent = p.percent != null ? p.percent : p.progress != null ? p.progress * 100 : undefined;
          if (percent != null) dispatch({ type: "progress", percent });
          if (p.message) dispatch({ type: "message", message: p.message });
          if (status === "completed" || status === "failed" || status === "cancelled") {
            dispatch({ type: "done", status, error: p.error ?? null });
            stopPoll();
          }
        } catch {
          // transient — keep polling
        }
      };
      void tick();
      pollRef.current = window.setInterval(tick, 2500);
    };

    // ---- Primary: Server-Sent Events. ----
    try {
      es = new EventSource(`${API_BASE}/stream/${encodeURIComponent(sceneId)}`);
    } catch {
      startPolling();
      return () => {
        closed = true;
        stopPoll();
      };
    }

    es.onopen = () => {
      if (!closed) dispatch({ type: "transport", transport: "sse" });
    };

    es.onmessage = (evt: MessageEvent<string>) => {
      if (closed) return;
      let data: Record<string, unknown>;
      try {
        data = JSON.parse(evt.data) as Record<string, unknown>;
      } catch {
        return;
      }
      switch (data.type) {
        case "state":
          dispatch({
            type: "state",
            status: String(data.state ?? ""),
            stage: bareStage(String(data.state ?? ""), data.current_stage as string | undefined),
          });
          break;
        case "progress":
          dispatch({ type: "progress", percent: Number(data.progress ?? 0) * 100 });
          break;
        case "log":
          if (typeof data.line === "string") dispatch({ type: "log", line: data.line });
          break;
        case "previews":
          if (data.previews && typeof data.previews === "object") {
            dispatch({ type: "previews", previews: data.previews as Record<string, string> });
          }
          break;
        case "done":
          dispatch({
            type: "done",
            status: String(data.state ?? "completed"),
            error: (data.error as string | null) ?? null,
          });
          es?.close();
          break;
        case "error":
          // Job-level error message from the stream — surface but let onerror
          // decide whether to fall back.
          if (typeof data.message === "string") dispatch({ type: "message", message: data.message });
          break;
        default:
          break;
      }
    };

    es.onerror = () => {
      // EventSource auto-reconnects; if we are not yet done, bring up polling as
      // a resilient fallback (covers proxies that buffer or drop SSE).
      if (closed) return;
      startPolling();
    };

    return () => {
      closed = true;
      stopPoll();
      es?.close();
    };
  }, [sceneId, active]);

  return state;
}
