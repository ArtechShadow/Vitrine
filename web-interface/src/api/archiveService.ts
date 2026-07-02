/**
 * User-facing archive API boundary.
 * Wraps existing backend calls and provides mocks where DreamLab endpoints are not ready.
 */

import {
  getScene,
  getTools,
  listScenes,
  runColmap,
  trainSplat,
  uploadVideo,
  type QaReport,
  type SceneDetail,
  type SceneMetadata,
  type ToolStatus,
} from "./client";
import { DEFAULT_QA_PRESET, getQaPreset } from "../lib/qaPresets";

export type InputSource = "video" | "photos" | "zip" | "folder" | "google_drive";

export type GoogleDriveContentType = "video" | "photos" | "zip" | "project" | "unknown";

export interface ArchiveJob {
  sceneId: string;
  status: string;
  inputSource: InputSource;
}

export interface GoogleDriveImportRequest {
  url: string;
  contentType: GoogleDriveContentType;
  title?: string;
}

export interface UploadImagesOptions {
  title?: string;
  autoProcess?: boolean;
}

export interface AdvancedBackendOptions {
  reconstructionBackend: string;
  splatEngine: string;
  meshEngine: string;
  objectEngine: string;
  unrealExportAvailable: boolean;
  dreamLabConnected: boolean;
}

// TODO(DreamLab): POST /api/scenes/upload-images when backend supports batch image ingest.
export async function uploadImages(
  files: File[],
  _options: UploadImagesOptions = {},
): Promise<ArchiveJob> {
  if (files.length === 0) throw new Error("Choose at least one photo.");
  await delay(800);
  console.warn("[archiveService] uploadImages is mocked — connect DreamLab image ingest endpoint.");
  return {
    sceneId: `mock-photos-${Date.now()}`,
    status: "created",
    inputSource: "photos",
  };
}

// TODO(DreamLab): POST /api/scenes/upload-zip when backend supports ZIP import.
export async function uploadZip(_file: File, _title?: string): Promise<ArchiveJob> {
  await delay(600);
  console.warn("[archiveService] uploadZip is mocked — connect DreamLab ZIP ingest endpoint.");
  return {
    sceneId: `mock-zip-${Date.now()}`,
    status: "created",
    inputSource: "zip",
  };
}

// TODO(DreamLab): POST /api/import/google-drive when backend supports shared link copy.
export async function importGoogleDriveLink(
  request: GoogleDriveImportRequest,
): Promise<ArchiveJob> {
  if (!request.url.trim()) throw new Error("Paste a shared Google Drive link.");
  await delay(1200);
  console.warn("[archiveService] importGoogleDriveLink is mocked — connect DreamLab Drive import.");
  return {
    sceneId: `mock-drive-${Date.now()}`,
    status: "created",
    inputSource: "google_drive",
  };
}

export async function createArchiveJob(
  source: InputSource,
  payload: File,
  options: { title?: string } = {},
): Promise<ArchiveJob> {
  if (source === "video") {
    const preset = getQaPreset(DEFAULT_QA_PRESET.id);
    const result = await uploadVideo(payload, {
      title: options.title ?? "",
      fps: preset.fps,
      autoExtract: true,
      qaPreset: DEFAULT_QA_PRESET.id,
      blurThreshold: preset.blurThreshold,
      duplicateThreshold: preset.duplicateThreshold,
    });
    return { sceneId: result.scene_id, status: result.metadata.status, inputSource: "video" };
  }
  throw new Error(`Unsupported createArchiveJob source: ${source}`);
}

export async function getArchiveJobStatus(sceneId: string): Promise<SceneDetail> {
  return getScene(sceneId);
}

export async function getQualityReport(sceneId: string): Promise<QaReport | null> {
  const detail = await getScene(sceneId);
  return detail.qa_report;
}

export async function getSceneList(): Promise<SceneMetadata[]> {
  return listScenes();
}

export async function getSceneDetails(sceneId: string): Promise<SceneDetail> {
  return getScene(sceneId);
}

// TODO(DreamLab): POST /api/scenes/{id}/export when ASP export package is ready.
export async function exportArchive(sceneId: string): Promise<{ downloadUrl: string }> {
  await delay(500);
  console.warn("[archiveService] exportArchive is mocked — connect ASP export endpoint.");
  return { downloadUrl: `/api/scenes/${sceneId}/splat/scene.ply` };
}

// TODO(DreamLab): POST /api/scenes/{id}/export/unreal when UE export path is ready.
export async function exportForGameEngine(_sceneId: string): Promise<{ status: string }> {
  await delay(500);
  console.warn("[archiveService] exportForGameEngine is mocked — connect DreamLab game engine export.");
  return { status: "queued" };
}

export const exportForUnreal = exportForGameEngine;

export async function getAdvancedBackendOptions(): Promise<AdvancedBackendOptions> {
  let tools: ToolStatus | null = null;
  try {
    tools = await getTools();
  } catch {
    tools = null;
  }
  return {
    reconstructionBackend: tools?.colmap?.available ? "COLMAP (camera tracking)" : "Not available",
    splatEngine: tools?.splat_training?.available ? "Nerfstudio Splatfacto" : "Not configured",
    meshEngine: "Experimental — DreamLab 2DGS/PGSR",
    objectEngine: "SAM3 / TRELLIS.2 (DreamLab)",
    unrealExportAvailable: false,
    dreamLabConnected: false,
  };
}

/** Start the standard archive build process for an existing scene. */
export async function startArchiveBuild(sceneId: string): Promise<void> {
  const detail = await getScene(sceneId);
  const status = detail.metadata.status;
  if (status === "frames_ready" || status === "created") {
    await runColmap(sceneId);
    return;
  }
  if (status === "colmap_ready" || status === "needs_rescan") {
    await trainSplat(sceneId);
    return;
  }
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
