import type {
  BranchInfo,
  ProgressInfo,
  SceneDetail,
  SceneMetadata,
  SystemStats,
  ToolStatus,
} from "./client";
import {
  INITIAL_DEMO_SCENES,
  PREVIEW_BRANCHES,
  PREVIEW_SYSTEM_STATS,
  PREVIEW_TOOLS,
  previewDerivativeUrl,
  previewSplatUrl,
  sceneDetailFor,
} from "./previewData";

let scenes = INITIAL_DEMO_SCENES.map((scene) => ({ ...scene }));

function delay(ms = 300): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function findScene(sceneId: string): SceneMetadata | undefined {
  return scenes.find((scene) => scene.scene_id === sceneId);
}

function upsertScene(meta: SceneMetadata): void {
  const index = scenes.findIndex((scene) => scene.scene_id === meta.scene_id);
  if (index >= 0) scenes[index] = meta;
  else scenes = [meta, ...scenes];
}

export async function listScenes(): Promise<SceneMetadata[]> {
  await delay();
  return scenes.map((scene) => ({ ...scene }));
}

export async function getScene(sceneId: string): Promise<SceneDetail> {
  await delay();
  const meta = findScene(sceneId);
  if (!meta) throw new Error("Scene not found");
  return sceneDetailFor(meta);
}

export async function getProgress(_sceneId: string, job = "colmap"): Promise<ProgressInfo> {
  await delay(150);
  return {
    job_type: job,
    status: "completed",
    stage: "done",
    stage_label: "Complete",
    stage_index: 4,
    stage_count: 4,
    percent: 100,
    message: "Preview mode — job already finished.",
    updated_at: new Date().toISOString(),
  };
}

export async function getSystemStats(): Promise<SystemStats> {
  await delay(100);
  return { ...PREVIEW_SYSTEM_STATS, updated_at: new Date().toISOString() };
}

export async function uploadVideo(
  file: File,
  options: { title?: string } = {},
): Promise<{ scene_id: string; metadata: SceneMetadata }> {
  await delay(900);
  const sceneId = `preview-${Date.now().toString(36)}`;
  const meta: SceneMetadata = {
    scene_id: sceneId,
    title: options.title?.trim() || file.name.replace(/\.[^.]+$/, ""),
    description: "",
    creator: "",
    location: "",
    capture_date: new Date().toISOString().slice(0, 10),
    capture_device: "Uploaded in preview",
    source_type: "video",
    source_filename: file.name,
    status: "frames_ready",
    processing_pipeline: { extract_frames: "completed" },
    outputs: {},
    extraction: { fps: 2, frame_count: 64 },
    notes: "Created in UI preview — processing is simulated.",
    rights: "",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  upsertScene(meta);
  return { scene_id: sceneId, metadata: meta };
}

export async function extractFrames(sceneId: string): Promise<void> {
  await delay(400);
  const meta = findScene(sceneId);
  if (!meta) throw new Error("Scene not found");
  upsertScene({ ...meta, status: "frames_ready", updated_at: new Date().toISOString() });
}

export async function runColmap(sceneId: string): Promise<void> {
  await delay(500);
  const meta = findScene(sceneId);
  if (!meta) throw new Error("Scene not found");
  upsertScene({
    ...meta,
    status: "colmap_ready",
    outputs: { ...meta.outputs, sparse_preview: "derivatives/sparse_preview.jpg" },
    colmap: {
      registered_images: 72,
      total_images: meta.extraction?.frame_count ?? 64,
      point_count: 41000,
      model_path: "colmap/sparse/0",
      success: true,
      registration_ratio: 0.9,
    },
    updated_at: new Date().toISOString(),
  });
}

export async function recoverColmap(sceneId: string): Promise<void> {
  return runColmap(sceneId);
}

export async function runQualityReconstruction(sceneId: string): Promise<void> {
  return runColmap(sceneId);
}

export async function trainSplat(sceneId: string): Promise<void> {
  await delay(600);
  const meta = findScene(sceneId);
  if (!meta) throw new Error("Scene not found");
  upsertScene({
    ...meta,
    status: "ready",
    outputs: {
      ...meta.outputs,
      splat: "splat/scene.ply",
      sparse_preview: meta.outputs.sparse_preview ?? "derivatives/sparse_preview.jpg",
      contact_sheet: "derivatives/contact_sheet.jpg",
    },
    splat: {
      path: "splat/scene.ply",
      iterations: 15000,
      size_bytes: 120000000,
      training_preset: "balanced",
    },
    updated_at: new Date().toISOString(),
  });
}

export async function importExternalSplat(
  sceneId: string,
  file: File,
  sourceLabel = "External splat",
): Promise<{ scene_id: string; external_splat: import("./client").ExternalSplat; metadata: SceneMetadata }> {
  await delay(500);
  const meta = findScene(sceneId);
  if (!meta) throw new Error("Scene not found");
  const external = {
    id: `ext-${Date.now()}`,
    source_label: sourceLabel || file.name,
    path: `derivatives/external/${file.name}`,
    size_bytes: file.size,
    imported_at: new Date().toISOString(),
    active: true,
  };
  const updated = {
    ...meta,
    external_splats: [...(meta.external_splats ?? []), external],
    active_splat_source: "external" as const,
    updated_at: new Date().toISOString(),
  };
  upsertScene(updated);
  return { scene_id: sceneId, external_splat: external, metadata: updated };
}

export async function setActiveSplat(
  sceneId: string,
  _source?: "native" | "external",
  _id?: string,
): Promise<SceneMetadata> {
  await delay(200);
  const meta = findScene(sceneId);
  if (!meta) throw new Error("Scene not found");
  return meta;
}

export async function runLingbot(_sceneId: string): Promise<void> {
  await delay(300);
}

export async function runPpisp(_sceneId: string): Promise<void> {
  await delay(300);
}

export async function runArtifixer(_sceneId: string): Promise<void> {
  await delay(300);
}

export async function getTools(): Promise<ToolStatus> {
  await delay(150);
  return PREVIEW_TOOLS;
}

export async function getBranches(): Promise<BranchInfo[]> {
  await delay(150);
  return PREVIEW_BRANCHES;
}

export async function updateMetadata(
  sceneId: string,
  patch: Partial<SceneMetadata>,
): Promise<SceneMetadata> {
  await delay(200);
  const meta = findScene(sceneId);
  if (!meta) throw new Error("Scene not found");
  const updated = { ...meta, ...patch, scene_id: meta.scene_id, updated_at: new Date().toISOString() };
  upsertScene(updated);
  return updated;
}

export async function deleteScene(sceneId: string): Promise<void> {
  await delay(250);
  scenes = scenes.filter((scene) => scene.scene_id !== sceneId);
}

export async function pauseJob(_sceneId: string, _job?: string): Promise<void> {
  await delay(150);
}

export async function resumeJob(_sceneId: string, _job?: string): Promise<void> {
  await delay(150);
}

export async function cancelJob(_sceneId: string, _job?: string): Promise<void> {
  await delay(150);
}

export async function regenerateSparsePreview(_sceneId: string): Promise<void> {
  await delay(200);
}

export function derivativeUrl(sceneId: string, path: string): string {
  return previewDerivativeUrl(sceneId, path);
}

export function splatUrl(sceneId: string, filename = "scene.ply"): string {
  return previewSplatUrl(sceneId, filename);
}

export function splatPathUrl(sceneId: string, path: string): string {
  if (path.startsWith("derivatives/")) {
    return derivativeUrl(sceneId, path.replace(/^derivatives\//, ""));
  }
  if (path.startsWith("splat/")) {
    return splatUrl(sceneId, path.replace(/^splat\//, ""));
  }
  return path;
}