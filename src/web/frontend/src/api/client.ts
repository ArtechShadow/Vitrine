// Vitrine backend contract (rewritten from PR #6's ArchiveSpace client against
// OUR loopback Flask API). Every path here is one the pipeline actually serves
// via the scenes_api / files_api / zip_api / splat_api blueprints or the
// existing job routes. Endpoints we deliberately do not build (per-stage job
// controls, energy, experimental branches) are absent — the UI gates those
// panels on /api/tools instead of calling missing routes.

import { del, getJson, postForm, postJson } from "./http";
import type { SceneTransform } from "../lib/sceneTransform";

/** Where a capture came from. Mirrors the backend `input_kind`. */
export type SourceType = "video" | "images" | "zip" | "google_drive";

/**
 * A scene is our job projected for the archive UI: scene_id === job_id.
 * Fields are normalized from whichever shape the backend returns (a scenes_api
 * document or a raw job summary), so the UI never depends on one exact schema.
 */
export interface SceneMetadata {
  scene_id: string;
  title: string;
  source_type: SourceType;
  status: string;
  filename?: string;
  file_size_bytes?: number;
  image_count?: number;
  progress: number; // 0..1
  current_stage?: string;
  created_at?: number | string;
  updated_at?: number | string;
  finished_at?: number | string | null;
  error?: string | null;
  /** Available derived artifacts, keyed by kind → relative path under the scene. */
  outputs?: Record<string, string>;
  /** Optional splat placement (harvested UX; only used if the backend supplies it). */
  sceneTransform?: Partial<SceneTransform> | null;
}

export interface ProgressInfo {
  status: string;
  stage: string;
  stage_label?: string;
  stage_index?: number;
  stage_count?: number;
  percent: number; // 0..100
  message?: string;
  log_tail?: string;
  updated_at?: number | string;
  error?: string | null;
}

export interface QaFrame {
  name: string;
  blur_score?: number;
  blurry?: boolean;
  duplicate?: boolean;
}

export interface QaReport {
  frame_count?: number;
  resolution?: { width: number; height: number };
  blur?: { average?: number; sharp_frame_count?: number; blurry_frame_count?: number };
  warnings?: string[];
  passed?: boolean;
  frames?: QaFrame[];
}

export interface SceneDetail {
  metadata: SceneMetadata;
  progress: ProgressInfo | null;
  qa_report: QaReport | null;
}

/** Capability flags used to gate optional panels. Everything is optional so a
 *  terse or partial /api/tools response degrades gracefully. */
export interface ToolStatus {
  ffmpeg?: { available: boolean; path?: string };
  colmap?: { available: boolean; path?: string };
  splat_training?: { available: boolean };
  mesh?: { available: boolean };
  objects?: { available: boolean };
  drive_ingest?: { available: boolean };
  /** Free-form feature switches consulted by the Pipeline / advanced panels. */
  features?: Record<string, boolean>;
}

// ---------------------------------------------------------------------------
// Normalization — tolerate both the scenes_api shape and a raw job summary.
// ---------------------------------------------------------------------------

type RawScene = Record<string, unknown> & {
  scene_id?: string;
  job_id?: string;
  status?: string;
  state?: string;
  source_type?: string;
  input_kind?: string;
};

function str(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : v == null ? fallback : String(v);
}

function num(v: unknown, fallback = 0): number {
  const n = typeof v === "number" ? v : typeof v === "string" ? Number(v) : NaN;
  return Number.isFinite(n) ? n : fallback;
}

function coerceSource(v: unknown): SourceType {
  const s = str(v).toLowerCase();
  if (s === "images" || s === "photos" || s === "image") return "images";
  if (s === "zip") return "zip";
  if (s === "google_drive" || s === "gdrive" || s === "drive") return "google_drive";
  return "video";
}

export function normalizeScene(raw: RawScene): SceneMetadata {
  const id = str(raw.scene_id ?? raw.job_id);
  return {
    scene_id: id,
    title: str(raw.title) || str(raw.filename) || id || "Untitled archive",
    source_type: coerceSource(raw.source_type ?? raw.input_kind),
    status: str(raw.status ?? raw.state, "unknown"),
    filename: str(raw.filename) || undefined,
    file_size_bytes: raw.file_size_bytes != null ? num(raw.file_size_bytes) : undefined,
    image_count: raw.image_count != null ? num(raw.image_count) : undefined,
    progress: num(raw.progress),
    current_stage: str(raw.current_stage) || undefined,
    created_at: (raw.created_at as number | string | undefined) ?? undefined,
    updated_at: (raw.updated_at as number | string | undefined) ?? undefined,
    finished_at: (raw.finished_at as number | string | null | undefined) ?? undefined,
    error: (raw.error as string | null | undefined) ?? undefined,
    outputs: (raw.outputs as Record<string, string> | undefined) ?? undefined,
    sceneTransform: (raw.sceneTransform as Partial<SceneTransform> | null | undefined) ?? undefined,
  };
}

function normalizeDetail(raw: unknown): SceneDetail {
  const obj = (raw ?? {}) as Record<string, unknown>;
  // Accept either { metadata, progress, qa_report } or a flat scene document.
  const metaSource = (obj.metadata as RawScene | undefined) ?? (obj as RawScene);
  const progress = (obj.progress as ProgressInfo | null | undefined) ?? null;
  const qa =
    (obj.qa_report as QaReport | null | undefined) ??
    (obj.qa as QaReport | null | undefined) ??
    null;
  return { metadata: normalizeScene(metaSource), progress, qa_report: qa };
}

// ---------------------------------------------------------------------------
// Scene endpoints (scenes_api)
// ---------------------------------------------------------------------------

export async function listScenes(): Promise<SceneMetadata[]> {
  const data = await getJson<RawScene[] | { scenes?: RawScene[] }>("/api/scenes", "Failed to load archives");
  const items = Array.isArray(data) ? data : (data.scenes ?? []);
  return items.map(normalizeScene).filter((s) => s.scene_id);
}

export async function getScene(sceneId: string): Promise<SceneDetail> {
  const data = await getJson<unknown>(`/api/scenes/${encodeURIComponent(sceneId)}`, "Failed to load archive");
  return normalizeDetail(data);
}

export function deleteScene(sceneId: string): Promise<void> {
  return del<void>(`/api/scenes/${encodeURIComponent(sceneId)}`, "Failed to remove archive");
}

// ---------------------------------------------------------------------------
// Capture ingestion (scenes_api + import)
// ---------------------------------------------------------------------------

export interface CreatedScene {
  scene_id: string;
  metadata?: SceneMetadata;
}

function readCreated(raw: Record<string, unknown>): CreatedScene {
  const scene_id = str(raw.scene_id ?? raw.job_id);
  const metadata = raw.metadata ? normalizeScene(raw.metadata as RawScene) : undefined;
  return { scene_id, metadata };
}

export async function uploadVideo(file: File, title = ""): Promise<CreatedScene> {
  const form = new FormData();
  form.append("file", file);
  if (title) form.append("title", title);
  const raw = await postForm<Record<string, unknown>>("/api/scenes/upload", form, "Upload failed");
  return readCreated(raw);
}

export async function uploadImages(files: File[], title = ""): Promise<CreatedScene> {
  if (files.length === 0) throw new Error("Choose at least one photo.");
  const form = new FormData();
  for (const f of files) form.append("files", f);
  if (title) form.append("title", title);
  const raw = await postForm<Record<string, unknown>>("/api/scenes/upload-images", form, "Photo upload failed");
  return readCreated(raw);
}

export async function uploadZip(file: File, title = ""): Promise<CreatedScene> {
  const form = new FormData();
  form.append("file", file);
  if (title) form.append("title", title);
  const raw = await postForm<Record<string, unknown>>("/api/scenes/upload-zip", form, "ZIP upload failed");
  return readCreated(raw);
}

export type DriveContentType = "video" | "photos" | "zip" | "unknown";

export async function importGoogleDrive(
  url: string,
  contentType: DriveContentType = "unknown",
  title = "",
): Promise<CreatedScene> {
  if (!url.trim()) throw new Error("Paste a shared Google Drive link.");
  const raw = await postJson<Record<string, unknown>>(
    "/api/import/google-drive",
    { url: url.trim(), content_type: contentType, title },
    "Google Drive import failed",
  );
  return readCreated(raw);
}

// ---------------------------------------------------------------------------
// Capability flags (feature gating)
// ---------------------------------------------------------------------------

export async function getTools(): Promise<ToolStatus> {
  return getJson<ToolStatus>("/api/tools", "Failed to check tools");
}

// ---------------------------------------------------------------------------
// URL builders (splat_api / files_api / zip_api). These return relative,
// same-origin URLs — safe to hand straight to <img>, <a download>, or the
// splat viewer without any cross-origin concern.
// ---------------------------------------------------------------------------

export function splatUrl(sceneId: string, filename = "scene.ksplat"): string {
  return `/api/scenes/${encodeURIComponent(sceneId)}/splat/${encodeURIComponent(filename)}`;
}

export function derivativeUrl(sceneId: string, path: string): string {
  return `/api/scenes/${encodeURIComponent(sceneId)}/derivatives/${path}`;
}

export function thumbnailUrl(scene: SceneMetadata): string | null {
  const out = scene.outputs ?? {};
  const stamp = scene.updated_at ? `?t=${encodeURIComponent(String(scene.updated_at))}` : "";
  if (out.contact_sheet) return derivativeUrl(scene.scene_id, "contact_sheet.jpg") + stamp;
  if (out.sparse_preview) return derivativeUrl(scene.scene_id, "sparse_preview.jpg") + stamp;
  return null;
}

/** Preferred splat artifact for a scene: our web deliverable is the .ksplat. */
export function sceneSplatUrl(scene: SceneMetadata): string | null {
  const out = scene.outputs ?? {};
  if (out.splat_ksplat) return splatUrl(scene.scene_id, out.splat_ksplat.split("/").pop() ?? "scene.ksplat");
  if (out.splat) return splatUrl(scene.scene_id, out.splat.split("/").pop() ?? "scene.ply");
  return null;
}

/**
 * Streamed per-run archive (zip_api), used directly as an `<a href download>`.
 * scene_id == job_id == run_id (1:1), so this points at zip_api's GET streamed
 * route — NOT scenes_api's POST /export (which is JSON pointer only and 405s on GET).
 */
export function exportUrl(sceneId: string): string {
  return `/api/runs/${encodeURIComponent(sceneId)}/zip`;
}
