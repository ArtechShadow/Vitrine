// Shared fetch helpers for the Vitrine backend.
//
// The backend is same-origin on the loopback Flask app; the API base is the
// empty string so every request is relative (`/api/...`, `/stream/...`). This
// keeps the SPA offline-signable and free of any cross-origin / CDN traffic.
//
// Error bodies are read leniently: our Flask handlers return `{ "error": ... }`
// while some newer blueprints follow the `{ "detail": ... }` convention. We
// accept either so the UI surfaces a useful message regardless of which
// handler answered.

/** Same-origin base. Intentionally empty — never point this at another host. */
export const API_BASE = "";

export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Pull a human-readable message out of an error response, accepting {detail} or {error}. */
export async function readError(res: Response, fallback: string): Promise<string> {
  try {
    const body = (await res.clone().json()) as { detail?: unknown; error?: unknown };
    const msg = body?.detail ?? body?.error;
    if (typeof msg === "string" && msg.trim()) return msg;
  } catch {
    // not JSON — fall through
  }
  try {
    const text = (await res.text()).trim();
    if (text && text.length < 300) return text;
  } catch {
    // ignore
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit, fallback = "Request failed"): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch (err) {
    // Network-level failure (backend down / tunnel closed).
    throw new ApiError(err instanceof Error ? err.message : "Network error", 0);
  }
  if (!res.ok) {
    throw new ApiError(await readError(res, fallback), res.status);
  }
  // 204 / empty body
  if (res.status === 204) return undefined as T;
  const ctype = res.headers.get("content-type") ?? "";
  if (!ctype.includes("application/json")) return undefined as T;
  return (await res.json()) as T;
}

export function getJson<T>(path: string, fallback?: string): Promise<T> {
  return request<T>(path, undefined, fallback);
}

export function postJson<T>(path: string, body?: unknown, fallback?: string): Promise<T> {
  return request<T>(
    path,
    {
      method: "POST",
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    },
    fallback,
  );
}

export function postForm<T>(path: string, form: FormData, fallback?: string): Promise<T> {
  return request<T>(path, { method: "POST", body: form }, fallback);
}

export function del<T>(path: string, fallback?: string): Promise<T> {
  return request<T>(path, { method: "DELETE" }, fallback);
}
