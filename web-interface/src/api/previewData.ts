import type {
  BranchInfo,
  ColmapReport,
  ProgressInfo,
  QaReport,
  SceneDetail,
  SceneMetadata,
  SystemStats,
  ToolStatus,
} from "./client";
import { DEMO_SPLAT_URL } from "../lib/previewMode";

const NOW = "2026-06-15T14:30:00.000Z";

function qaReport(frameCount = 84): QaReport {
  return {
    frame_count: frameCount,
    resolution: { width: 1920, height: 1080 },
    qa_preset: "balanced",
    qa_settings: { blur_threshold: 120, duplicate_threshold: 0.92 },
    blur: { average: 142, sharp_frame_count: 71, blurry_frame_count: 13 },
    warnings: ["13 frames are slightly blurry — still usable for reconstruction."],
    passed: true,
  };
}

function colmapReport(): ColmapReport {
  return {
    success: true,
    registered_images: 78,
    total_images: 84,
    point_count: 48210,
    registration_ratio: 0.93,
    mean_reprojection_error: 0.84,
    warnings: [],
    passed: true,
  };
}

function readyScene(): SceneMetadata {
  return {
    scene_id: "demo-xr-lab",
    title: "XR Lab — reference capture",
    description: "University of Salford XR Lab walkthrough used for ArchiveSpace UI preview.",
    creator: "DreamLab",
    location: "Salford, UK",
    capture_date: "2026-05-12",
    capture_device: "iPhone 15 Pro",
    source_type: "video",
    source_filename: "XR_Lab_walkthrough.mp4",
    status: "ready",
    processing_pipeline: {
      extract_frames: "completed",
      run_colmap: "completed",
      train_splat: "completed",
    },
    outputs: {
      splat: "splat/scene.ply",
      sparse_preview: "derivatives/sparse_preview.jpg",
      contact_sheet: "derivatives/contact_sheet.jpg",
    },
    extraction: {
      fps: 2,
      frame_count: 84,
      qa_preset: "balanced",
      qa_settings: { blur_threshold: 120, duplicate_threshold: 0.92 },
    },
    colmap: {
      registered_images: 78,
      total_images: 84,
      point_count: 48210,
      model_path: "colmap/sparse/0",
      success: true,
      registration_ratio: 0.93,
      mean_reprojection_error: 0.84,
    },
    splat: {
      path: "splat/scene.ply",
      iterations: 15000,
      size_bytes: 273733021,
      downscale_factor: 1,
      gpu_tier: "high",
      training_preset: "balanced",
    },
    notes: "Demo archive for shared UI preview.",
    rights: "University of Salford — internal preview",
    created_at: "2026-06-10T09:00:00.000Z",
    updated_at: NOW,
    energy_cost: {
      energy_wh: 142.5,
      cost_pence: 4.2,
      rate_pence_per_kwh: 29.5,
      updated_at: NOW,
    },
  };
}

function processingScene(): SceneMetadata {
  return {
    scene_id: "demo-gallery-walk",
    title: "Gallery walkthrough",
    description: "Simulated in-progress archive for preview.",
    creator: "Curator demo",
    location: "Whitworth Art Gallery",
    capture_date: "2026-06-01",
    capture_device: "GoPro Hero 12",
    source_type: "video",
    source_filename: "gallery_walk.mp4",
    status: "training",
    processing_pipeline: {
      extract_frames: "completed",
      run_colmap: "completed",
      train_splat: "running",
    },
    outputs: {
      sparse_preview: "derivatives/sparse_preview.jpg",
    },
    extraction: { fps: 2, frame_count: 112 },
    colmap: {
      registered_images: 96,
      total_images: 112,
      point_count: 52100,
      model_path: "colmap/sparse/0",
      success: true,
      registration_ratio: 0.86,
    },
    notes: "",
    rights: "",
    created_at: "2026-06-14T11:20:00.000Z",
    updated_at: NOW,
  };
}

function needsRescanScene(): SceneMetadata {
  return {
    scene_id: "demo-needs-rescan",
    title: "Sculpture court — first attempt",
    description: "Example archive that needs another capture pass.",
    creator: "Field team",
    location: "Ordsall Hall",
    capture_date: "2026-05-28",
    capture_device: "iPhone 14",
    source_type: "photos",
    status: "needs_rescan",
    processing_pipeline: {
      extract_frames: "completed",
      run_colmap: "completed",
    },
    outputs: {
      sparse_preview: "derivatives/sparse_preview.jpg",
    },
    extraction: { fps: 0, frame_count: 48 },
    colmap: {
      registered_images: 19,
      total_images: 48,
      point_count: 4200,
      model_path: "colmap/sparse/0",
      success: false,
      registration_ratio: 0.4,
    },
    rescan_advice: [
      "Capture more overlapping photos around the sculpture.",
      "Move slower and keep the subject centred in frame.",
      "Avoid shooting into direct sunlight.",
    ],
    notes: "",
    rights: "",
    created_at: "2026-05-29T16:45:00.000Z",
    updated_at: NOW,
  };
}

export const INITIAL_DEMO_SCENES: SceneMetadata[] = [
  readyScene(),
  processingScene(),
  needsRescanScene(),
];

export function sceneDetailFor(meta: SceneMetadata): SceneDetail {
  const ready = meta.status === "ready";
  const training = meta.status === "training";
  const trainProgress: ProgressInfo | null = training
    ? {
        job_type: "train_splat",
        status: "running",
        stage: "train",
        stage_label: "Building 3D scene",
        stage_index: 2,
        stage_count: 3,
        percent: 62,
        message: "Training Gaussian splat — about halfway…",
        eta_seconds: 840,
        updated_at: NOW,
      }
    : null;

  return {
    metadata: meta,
    splat_readiness: ready
      ? {
          ready: true,
          registered_images: meta.colmap?.registered_images ?? 0,
          total_images: meta.colmap?.total_images ?? 0,
          registration_ratio: meta.colmap?.registration_ratio ?? 1,
          blockers: [],
        }
      : {
          ready: false,
          registered_images: meta.colmap?.registered_images ?? 0,
          total_images: meta.colmap?.total_images ?? 0,
          registration_ratio: meta.colmap?.registration_ratio ?? 0,
          blockers: meta.status === "needs_rescan" ? ["Low camera registration — rescan recommended"] : ["Splat training in progress"],
        },
    qa_report: meta.extraction ? qaReport(meta.extraction.frame_count) : null,
    qa_progress: null,
    colmap_report: meta.colmap ? colmapReport() : null,
    recovery_report: null,
    progress: trainProgress,
    progress_extract: null,
    progress_colmap: null,
    progress_recovery: null,
    progress_lingbot: null,
    progress_ppisp: null,
    progress_artifixer: null,
    progress_train: trainProgress,
    energy: ready
      ? {
          rate_pence_per_kwh: 29.5,
          energy_wh: 142.5,
          cost_pence: 4.2,
          updated_at: NOW,
        }
      : null,
    job: training ? { status: "running", type: "train_splat", progress: trainProgress ?? undefined } : null,
    jobs: training && trainProgress ? { train_splat: { status: "running", type: "train_splat", progress: trainProgress } } : {},
  };
}

export function previewSplatUrl(sceneId: string, filename = "scene.ply"): string {
  if (sceneId === "demo-xr-lab" && filename === "scene.ply") {
    return DEMO_SPLAT_URL;
  }
  return DEMO_SPLAT_URL;
}

export function previewDerivativeUrl(_sceneId: string, path: string): string {
  if (path.includes("sparse_preview") || path.includes("contact_sheet")) {
    return "/logo.jpg";
  }
  return "/logo.jpg";
}

export const PREVIEW_TOOLS: ToolStatus = {
  ffmpeg: { available: true, path: "preview://ffmpeg" },
  colmap: { available: true, path: "preview://colmap" },
  splat_training: { available: true, python: "preview://nerfstudio", doc: "Simulated for UI preview" },
  gpu_profile: {
    tier: "preview",
    name: "Preview GPU (simulated)",
    vram_total_mb: 12288,
    recommended_iterations: 15000,
    downscale_factor: 1,
    extract_fps: 2,
    recommended_splat_preset: "balanced",
    target_hardware: "Any — preview mode",
    note: "Pipeline tools are simulated in this hosted preview.",
  },
};

export const PREVIEW_BRANCHES: BranchInfo[] = [
  {
    id: "lingbot-map",
    name: "LingBot-Map",
    purpose: "Fast neural preview branch",
    status: "preview",
    env_vars: ["VITRINE_LINGBOT_REPO"],
    install_doc: "docs/branches/lingbot-map.md",
    repo_url: "",
  },
  {
    id: "ppisp",
    name: "PPiSP",
    purpose: "Photorealistic mesh experiments",
    status: "preview",
    env_vars: ["VITRINE_PPISP_REPO"],
    install_doc: "docs/branches/ppisp.md",
    repo_url: "",
  },
];

export const PREVIEW_SYSTEM_STATS: SystemStats = {
  updated_at: NOW,
  cpu_percent: 24,
  ram_used_gb: 11.2,
  ram_total_gb: 32,
  ram_percent: 35,
  gpu_available: true,
  gpu_name: "Preview GPU",
  gpu_percent: 41,
  vram_used_mb: 6200,
  vram_total_mb: 12288,
  vram_percent: 50,
  gpu_power_w: 180,
  cpu_power_est_w: 65,
  total_power_w: 245,
  power_note: "Simulated stats for UI preview",
};