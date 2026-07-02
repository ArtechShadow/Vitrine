import { isPreviewMode } from "../lib/previewMode";

const API = "/api";

export interface FrameList {
  total: number;
  offset: number;
  limit: number;
  frames: string[];
}

export async function listFrames(
  sceneId: string,
  limit = 120,
  offset = 0,
): Promise<FrameList> {
  if (isPreviewMode) {
    await new Promise((resolve) => window.setTimeout(resolve, 200));
    return { total: 0, offset, limit, frames: [] };
  }
  const res = await fetch(`${API}/scenes/${sceneId}/frames?limit=${limit}&offset=${offset}`);
  if (!res.ok) throw new Error("Failed to load frames");
  return res.json();
}

export function frameUrl(sceneId: string, frameName: string): string {
  const clean = frameName.replace(/^frames\//, "");
  return `${API}/scenes/${encodeURIComponent(sceneId)}/frames/${encodeURIComponent(clean)}`;
}

export interface FrameCullResult {
  removed: string[];
  removed_count: number;
  remaining: number;
}

export async function cullFrames(sceneId: string, remove: string[]): Promise<FrameCullResult> {
  if (isPreviewMode) {
    return { removed: remove, removed_count: remove.length, remaining: 0 };
  }
  const res = await fetch(`${API}/scenes/${sceneId}/frames/cull`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ remove }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to remove frames");
  }
  return res.json();
}