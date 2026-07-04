// Frame browsing (files_api). Read-only in v1 — the gallery and QA review show
// extracted frames and their QA verdicts but do not cull. Served same-origin.

import { getJson } from "./http";

export interface FrameList {
  total: number;
  offset: number;
  limit: number;
  frames: string[];
}

export async function listFrames(sceneId: string, limit = 120, offset = 0): Promise<FrameList> {
  const data = await getJson<Partial<FrameList>>(
    `/api/scenes/${encodeURIComponent(sceneId)}/frames?limit=${limit}&offset=${offset}`,
    "Failed to load frames",
  );
  return {
    total: data.total ?? data.frames?.length ?? 0,
    offset: data.offset ?? offset,
    limit: data.limit ?? limit,
    frames: data.frames ?? [],
  };
}

export function frameUrl(sceneId: string, frameName: string): string {
  const clean = frameName.replace(/^frames\//, "");
  return `/api/scenes/${encodeURIComponent(sceneId)}/frames/${encodeURIComponent(clean)}`;
}
