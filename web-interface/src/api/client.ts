import { isPreviewMode } from "../lib/previewMode";
import * as previewApi from "./previewApi";

export interface SceneMetadata {
  scene_id: string;
  title: string;
  description: string;
  creator: string;
  location: string;
  capture_date: string;
  capture_device: string;
  source_type: string;
  source_filename?: string;
  status: string;
  processing_pipeline: Record<string, string>;
  outputs: Record<string, string>;
  external_splats?: ExternalSplat[];
  active_splat_source?: "native" | "external";
  extraction?: {
    fps: number;
    frame_count: number;
    qa_preset?: string;
    qa_settings?: {
      blur_threshold: number;
      duplicate_threshold: number;
    };
  };
  colmap?: {
    registered_images: number;
    total_images: number;
    point_count: number;
    model_path: string;
    success: boolean;
    registration_ratio?: number;
    mean_reprojection_error?: number;
  };
  colmap_recovery?: {
    completed_at?: string;
    initial_ratio?: number;
    best_attempt?: string;
    best_ratio?: number;
    best_fps?: number;
    needs_rescan?: boolean;
    experimental_deblur_used?: boolean;
  };
  rescan_advice?: string[];
  splat?: {
    path: string;
    iterations: number;
    size_bytes: number;
    downscale_factor?: number;
    gpu_tier?: string;
    training_preset?: string;
    preview?: boolean;
    ppisp_manifest?: string;
    quality_flags?: Record<string, unknown>;
  };
  branches?: Record<string, { status: string; preview?: string }>;
  notes: string;
  rights: string;
  created_at: string;
  updated_at: string;
  last_error?: string;
  energy_cost?: {
    energy_wh: number;
    cost_pence: number;
    rate_pence_per_kwh: number;
    updated_at: string;
  };
  quality_flags?: Record<string, {
    reason?: string;
    best_attempt?: string;
    registered_images?: number;
    point_count?: number;
  }>;
  sceneTransform?: {
    rotationDeg: { x: number; y: number; z: number };
    position: { x: number; y: number; z: number };
    scale: number;
    center: boolean;
  };
}

export interface ExternalSplat {
  id: string;
  source_label: string;
  path: string;
  size_bytes: number;
  imported_at: string;
  active: boolean;
}

export interface QaFrame {
  name: string;
  blur_score: number;
  blurry: boolean;
  duplicate: boolean;
}

export interface QaProgress {
  status: string;
  analyzed: number;
  frames: QaFrame[];
  updated_at?: string;
}

export interface QaReport {
  frame_count: number;
  resolution: { width: number; height: number };
  qa_preset?: string;
  qa_settings?: {
    blur_threshold: number;
    duplicate_threshold: number;
  };
  blur: {
    average: number;
    sharp_frame_count: number;
    blurry_frame_count: number;
  };
  warnings: string[];
  passed: boolean;
  frames?: QaFrame[];
}

export interface ColmapReport {
  success: boolean;
  registered_images: number;
  total_images: number;
  point_count: number;
  registration_ratio: number;
  mean_reprojection_error?: number;
  warnings: string[];
  passed: boolean;
  advice?: string;
  recovery?: boolean;
  recovery_attempt?: string;
}

export interface RecoveryReport {
  generated_at: string;
  initial_registration_ratio: number;
  best_attempt_id: string;
  best_registration_ratio: number;
  best_mean_reprojection_error?: number | null;
  needs_rescan: boolean;
  experimental_deblur_used: boolean;
  synthetic_frames_used: boolean;
  fps_candidates: number[];
  matcher: string;
  rescan_advice: string[];
  attempts: Array<{
    id: string;
    fps?: number;
    registration_ratio?: number;
    registered_images?: number;
    total_images?: number;
    mean_reprojection_error?: number | null;
    experimental?: boolean;
    keyframe_count?: number;
  }>;
}

export interface ProgressInfo {
  job_type: string;
  status: string;
  stage: string;
  stage_label?: string;
  stage_index: number;
  stage_count: number;
  percent: number;
  message: string;
  log_tail?: string;
  eta_seconds?: number | null;
  preview?: string;
  metrics?: Record<string, number | string>;
  updated_at?: string;
  energy?: {
    energy_wh: number;
    cost_pence: number;
    rate_pence_per_kwh: number;
  };
  error?: string;
}

export interface JobInfo {
  status: string;
  type?: string;
  error?: string;
  progress?: ProgressInfo;
}

export interface SystemStats {
  updated_at: string;
  cpu_percent: number;
  ram_used_gb: number;
  ram_total_gb: number;
  ram_percent: number;
  gpu_available: boolean;
  gpu_name: string;
  gpu_percent: number;
  vram_used_mb: number;
  vram_total_mb: number;
  vram_percent: number;
  gpu_power_w: number | null;
  cpu_power_est_w: number;
  total_power_w: number;
  power_note: string;
}

export interface BranchInfo {
  id: string;
  name: string;
  purpose: string;
  status: string;
  env_vars: string[];
  install_doc: string;
  repo_url: string;
  paths?: Record<string, string>;
}

export interface EnergyJobSummary {
  energy_wh: number;
  cost_pence: number;
  duration_s?: number;
  finalized?: boolean;
  started_at?: string;
  completed_at?: string;
}

export interface EnergyLogEntry {
  at: string;
  job: string;
  job_energy_wh: number;
  job_cost_pence: number;
  total_energy_wh: number;
  total_cost_pence: number;
  message: string;
}

export interface EnergySummary {
  rate_pence_per_kwh: number;
  energy_wh: number;
  cost_pence: number;
  updated_at: string;
  jobs?: Record<string, EnergyJobSummary>;
  log?: EnergyLogEntry[];
}

export interface SceneDetail {
  metadata: SceneMetadata;
  splat_readiness?: SplatReadiness;
  qa_report: QaReport | null;
  qa_progress: QaProgress | null;
  colmap_report: ColmapReport | null;
  recovery_report: RecoveryReport | null;
  progress: ProgressInfo | null;
  progress_extract: ProgressInfo | null;
  progress_colmap: ProgressInfo | null;
  progress_recovery: ProgressInfo | null;
  progress_lingbot: ProgressInfo | null;
  progress_ppisp: ProgressInfo | null;
  progress_artifixer: ProgressInfo | null;
  progress_train: ProgressInfo | null;
  energy: EnergySummary | null;
  job: JobInfo | null;
  jobs: Record<string, JobInfo>;
}

export interface GpuProfile {
  tier: string;
  name: string;
  vram_total_mb: number;
  recommended_iterations: number;
  downscale_factor: number;
  extract_fps: number;
  recommended_splat_preset?: string;
  target_hardware: string;
  note: string;
}

export interface SplatReadiness {
  ready: boolean;
  registered_images: number;
  total_images: number;
  registration_ratio: number;
  blockers: string[];
}

export interface ToolStatus {
  ffmpeg: { available: boolean; path: string };
  colmap: { available: boolean; path: string };
  lingbot_map?: { available: boolean };
  ppisp?: { available: boolean; doc: string };
  nvidia_artifixer?: { available: boolean; doc: string };
  splat_training?: { available: boolean; python: string; doc: string };
  gpu_profile?: GpuProfile;
  branches?: BranchInfo[];
}

const API = "/api";

export async function listScenes(): Promise<SceneMetadata[]> {
  if (isPreviewMode) return previewApi.listScenes();
  const res = await fetch(`${API}/scenes`);
  if (!res.ok) throw new Error("Failed to load scenes");
  return res.json();
}

export async function getScene(sceneId: string): Promise<SceneDetail> {
  if (isPreviewMode) return previewApi.getScene(sceneId);
  const res = await fetch(`${API}/scenes/${sceneId}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    if (res.status === 404) throw new Error("Scene not found");
    throw new Error((err as { detail?: string }).detail ?? `Failed to load scene (${res.status})`);
  }
  return res.json();
}

export async function getProgress(sceneId: string, job = "colmap"): Promise<ProgressInfo> {
  if (isPreviewMode) return previewApi.getProgress(sceneId, job);
  const res = await fetch(`${API}/scenes/${sceneId}/progress?job=${job}`);
  if (!res.ok) throw new Error("Failed to load progress");
  return res.json();
}

export async function getSystemStats(): Promise<SystemStats> {
  if (isPreviewMode) return previewApi.getSystemStats();
  const res = await fetch(`${API}/system/stats`);
  if (!res.ok) throw new Error("Failed to load system stats");
  return res.json();
}

export async function uploadVideo(
  file: File,
  options: {
    title?: string;
    fps?: number;
    autoExtract?: boolean;
    qaPreset?: string;
    blurThreshold?: number;
    duplicateThreshold?: number;
  },
): Promise<{ scene_id: string; metadata: SceneMetadata }> {
  if (isPreviewMode) return previewApi.uploadVideo(file, options);
  const form = new FormData();
  form.append("file", file);
  form.append("title", options.title ?? "");
  form.append("fps", String(options.fps ?? 2));
  form.append("auto_extract", String(options.autoExtract ?? true));
  form.append("qa_preset", options.qaPreset ?? "balanced");
  if (options.blurThreshold != null) form.append("blur_threshold", String(options.blurThreshold));
  if (options.duplicateThreshold != null) form.append("duplicate_threshold", String(options.duplicateThreshold));

  const res = await fetch(`${API}/scenes/upload`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Upload failed");
  }
  return res.json();
}

export async function extractFrames(
  sceneId: string,
  fps = 2,
  autoColmap = true,
  options: { qaPreset?: string; blurThreshold?: number; duplicateThreshold?: number } = {},
): Promise<void> {
  if (isPreviewMode) return previewApi.extractFrames(sceneId);
  const params = new URLSearchParams({
    fps: String(fps),
    auto_colmap: String(autoColmap),
    qa_preset: options.qaPreset ?? "balanced",
  });
  if (options.blurThreshold != null) params.set("blur_threshold", String(options.blurThreshold));
  if (options.duplicateThreshold != null) params.set("duplicate_threshold", String(options.duplicateThreshold));
  const res = await fetch(`${API}/scenes/${sceneId}/extract-frames?${params}`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to start extraction");
}

export async function runColmap(sceneId: string): Promise<void> {
  if (isPreviewMode) return previewApi.runColmap(sceneId);
  const res = await fetch(`${API}/scenes/${sceneId}/run-colmap`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to start COLMAP");
  }
}

export async function recoverColmap(
  sceneId: string,
  options: { experimentalDeblur?: boolean; force?: boolean } = {},
): Promise<void> {
  if (isPreviewMode) return previewApi.recoverColmap(sceneId);
  const params = new URLSearchParams();
  if (options.experimentalDeblur) params.set("experimental_deblur", "true");
  if (options.force) params.set("force", "true");
  const qs = params.toString();
  const res = await fetch(
    `${API}/scenes/${sceneId}/recover-colmap${qs ? `?${qs}` : ""}`,
    { method: "POST" },
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to start COLMAP recovery");
  }
}

export async function runQualityReconstruction(sceneId: string): Promise<void> {
  if (isPreviewMode) return previewApi.runQualityReconstruction(sceneId);
  const res = await fetch(`${API}/scenes/${sceneId}/quality-reconstruction`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to start quality reconstruction");
  }
}

export async function trainSplat(
  sceneId: string,
  options: { preset?: string; iterations?: number; downscaleFactor?: number } = {},
): Promise<void> {
  if (isPreviewMode) return previewApi.trainSplat(sceneId);
  const params = new URLSearchParams();
  if (options.preset) params.set("preset", options.preset);
  if (options.iterations != null) params.set("iterations", String(options.iterations));
  if (options.downscaleFactor != null) params.set("downscale_factor", String(options.downscaleFactor));
  const qs = params.toString();
  const res = await fetch(`${API}/scenes/${sceneId}/train-splat${qs ? `?${qs}` : ""}`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to start splat training");
  }
}

export async function importExternalSplat(
  sceneId: string,
  file: File,
  sourceLabel = "External splat",
): Promise<{ scene_id: string; external_splat: ExternalSplat; metadata: SceneMetadata }> {
  if (isPreviewMode) return previewApi.importExternalSplat(sceneId, file, sourceLabel);
  const form = new FormData();
  form.append("file", file);
  form.append("source_label", sourceLabel);
  const res = await fetch(`${API}/scenes/${sceneId}/import-splat`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to import splat");
  }
  return res.json();
}

export async function setActiveSplat(
  sceneId: string,
  source: "native" | "external",
  id?: string,
): Promise<SceneMetadata> {
  if (isPreviewMode) return previewApi.setActiveSplat(sceneId);
  const res = await fetch(`${API}/scenes/${sceneId}/active-splat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source, id }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to switch splat preview");
  }
  return res.json();
}

export async function runLingbot(sceneId: string): Promise<void> {
  if (isPreviewMode) return previewApi.runLingbot(sceneId);
  const res = await fetch(`${API}/scenes/${sceneId}/run-lingbot`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to start LingBot-Map preview");
}

export async function runPpisp(sceneId: string, options: { cameraCount?: number } = {}): Promise<void> {
  if (isPreviewMode) return previewApi.runPpisp(sceneId);
  const params = new URLSearchParams();
  if (options.cameraCount != null) params.set("camera_count", String(options.cameraCount));
  const q = params.toString() ? `?${params}` : "";
  const res = await fetch(`${API}/scenes/${sceneId}/run-ppisp${q}`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to start PPiSP prep");
  }
}

export type ArtiFixerVariant = "artifixer" | "artifixer3d" | "artifixer3d_plus";
export type ArtiFixerTrajectory = "val_frames" | "all_frames" | "trajectory";

export async function runArtifixer(
  sceneId: string,
  options: {
    variant?: ArtiFixerVariant;
    renderTrajectory?: ArtiFixerTrajectory;
    runPrep?: boolean;
  } = {},
): Promise<void> {
  if (isPreviewMode) return previewApi.runArtifixer(sceneId);
  const params = new URLSearchParams();
  if (options.variant) params.set("variant", options.variant);
  if (options.renderTrajectory) params.set("render_trajectory", options.renderTrajectory);
  if (options.runPrep) params.set("run_prep", "true");
  const q = params.toString() ? `?${params}` : "";
  const res = await fetch(`${API}/scenes/${sceneId}/run-artifixer${q}`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to start ArtiFixer prep");
  }
}

export async function getTools(): Promise<ToolStatus> {
  if (isPreviewMode) return previewApi.getTools();
  const res = await fetch(`${API}/tools`);
  if (!res.ok) throw new Error("Failed to check tools");
  return res.json();
}

export async function getBranches(): Promise<BranchInfo[]> {
  if (isPreviewMode) return previewApi.getBranches();
  const res = await fetch(`${API}/branches`);
  if (!res.ok) throw new Error("Failed to load branches");
  return res.json();
}

export async function updateMetadata(
  sceneId: string,
  patch: Partial<SceneMetadata>,
): Promise<SceneMetadata> {
  if (isPreviewMode) return previewApi.updateMetadata(sceneId, patch);
  const res = await fetch(`${API}/scenes/${sceneId}/metadata`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error("Failed to update metadata");
  return res.json();
}

export function derivativeUrl(sceneId: string, path: string): string {
  if (isPreviewMode) return previewApi.derivativeUrl(sceneId, path);
  return `${API}/scenes/${sceneId}/derivatives/${path}`;
}

export function contactSheetUrl(sceneId: string): string {
  return derivativeUrl(sceneId, "contact_sheet.jpg");
}

export function sparsePreviewUrl(sceneId: string): string {
  return derivativeUrl(sceneId, "sparse_preview.jpg");
}

export function splatUrl(sceneId: string, filename = "scene.ply"): string {
  if (isPreviewMode) return previewApi.splatUrl(sceneId, filename);
  return `${API}/scenes/${sceneId}/splat/${filename}`;
}

export function splatPathUrl(sceneId: string, path: string): string {
  if (isPreviewMode) return previewApi.splatPathUrl(sceneId, path);
  if (path.startsWith("derivatives/")) {
    return derivativeUrl(sceneId, path.replace(/^derivatives\//, ""));
  }
  if (path.startsWith("splat/")) {
    return splatUrl(sceneId, path.replace(/^splat\//, ""));
  }
  return path;
}

export function formatEnergyCost(pence: number): string {
  if (pence < 10) return `${pence.toFixed(2)}p`;
  if (pence < 100) return `${pence.toFixed(1)}p`;
  return `£${(pence / 100).toFixed(2)}`;
}

export function formatEta(seconds: number | null | undefined): string {
  if (seconds == null || seconds <= 0) return "calculating…";
  if (seconds < 60) return `~${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s > 0 ? `~${m}m ${s}s` : `~${m}m`;
}

export type { FrameCullResult, FrameList } from "./frames";
export { cullFrames, frameUrl, listFrames } from "./frames";

export async function deleteScene(sceneId: string): Promise<void> {
  if (isPreviewMode) return previewApi.deleteScene(sceneId);
  const res = await fetch(`${API}/scenes/${sceneId}`, { method: "DELETE" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to delete scene");
  }
}

export async function pauseJob(sceneId: string, job?: string): Promise<void> {
  if (isPreviewMode) return previewApi.pauseJob(sceneId, job);
  const q = job ? `?job=${encodeURIComponent(job)}` : "";
  const res = await fetch(`${API}/scenes/${sceneId}/jobs/pause${q}`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to pause job");
  }
}

export async function resumeJob(sceneId: string, job?: string): Promise<void> {
  if (isPreviewMode) return previewApi.resumeJob(sceneId, job);
  const q = job ? `?job=${encodeURIComponent(job)}` : "";
  const res = await fetch(`${API}/scenes/${sceneId}/jobs/resume${q}`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to resume job");
  }
}

export async function cancelJob(sceneId: string, job?: string, pipeline = true): Promise<void> {
  if (isPreviewMode) return previewApi.cancelJob(sceneId, job);
  const params = new URLSearchParams();
  if (job) params.set("job", job);
  if (!pipeline) params.set("pipeline", "false");
  const q = params.toString() ? `?${params}` : "";
  const res = await fetch(`${API}/scenes/${sceneId}/jobs/cancel${q}`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to cancel job");
  }
}

export async function regenerateSparsePreview(sceneId: string): Promise<void> {
  if (isPreviewMode) return previewApi.regenerateSparsePreview(sceneId);
  const res = await fetch(`${API}/scenes/${sceneId}/regenerate-preview`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to regenerate preview");
  }
}

export function sceneThumbnailUrl(scene: SceneMetadata): string | null {
  if (scene.outputs?.contact_sheet) {
    return contactSheetUrl(scene.scene_id) + `?t=${scene.updated_at}`;
  }
  if (scene.outputs?.sparse_preview || scene.status === "colmap_ready" || scene.status === "ready") {
    return sparsePreviewUrl(scene.scene_id) + `?t=${scene.updated_at}`;
  }
  return null;
}

export function formatStatus(status: string): string {
  if (status === "needs_rescan") return "Needs rescan";
  if (status === "colmap_recovery_running") return "COLMAP recovery running";
  return status.replace(/_/g, " ");
}

const RUNNING = new Set([
  "created",
  "extracting_frames",
  "colmap_running",
  "colmap_recovery_running",
  "training",
]);

export function isSceneBusy(status: string): boolean {
  return RUNNING.has(status);
}
