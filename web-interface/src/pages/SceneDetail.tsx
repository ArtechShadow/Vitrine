import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import ExperimentalBranches from "../components/ExperimentalBranches";
import ExtractionBackdrop from "../components/ExtractionBackdrop";
import QaSwipeReview from "../components/QaSwipeReview";
import FrameExtractionPanel from "../components/FrameExtractionPanel";
import PipelineTrack from "../components/PipelineTrack";
import ProcessingPanel from "../components/ProcessingPanel";
import EnergyCostPanel from "../components/EnergyCostPanel";
import SystemStatsBar from "../components/SystemStatsBar";
import AlignmentProcessPanel from "../components/AlignmentProcessPanel";
import SceneAlignmentPanel from "../components/SceneAlignmentPanel";
import SparsePointViewer from "../components/SparsePointViewer";
import SplatViewer from "../components/SplatViewer";
import ContactSheetGallery from "../components/ContactSheetGallery";
import ConfirmDialog from "../components/ConfirmDialog";
import {
  deleteScene,
  derivativeUrl,
  extractFrames,
  frameUrl,
  formatEnergyCost,
  formatStatus,
  getScene,
  getSystemStats,
  getTools,
  importExternalSplat,
  isSceneBusy,
  recoverColmap,
  runColmap,
  setActiveSplat,
  sparsePreviewUrl,
  splatPathUrl,
  trainSplat,
  updateMetadata,
  type ColmapReport,
  type RecoveryReport,
  type ProgressInfo,
  type QaProgress,
  type QaReport,
  type EnergySummary,
  type ExternalSplat,
  type SceneMetadata,
  type SplatReadiness,
  type SystemStats,
  type ToolStatus,
} from "../api/client";
import { DEFAULT_QA_PRESET, getQaPreset, QA_PRESETS, type QaPresetId } from "../lib/qaPresets";
import FriendlyStatusMessage from "../components/FriendlyStatusMessage";
import { friendlyStatus } from "../lib/friendlyStatus";
import {
  defaultSplatPresetForGpu,
  getSplatPreset,
  resolveSplatPresetSettings,
  SPLAT_PRESETS,
  type SplatPresetId,
} from "../lib/splatPresets";

type PreviewTab = "sparse" | "transform" | "alignment" | "contact" | "lingbot";

function statusBadgeClass(status: string) {
  if (status.includes("failed") || status === "needs_rescan") return "error";
  if (status === "frames_ready" || status === "colmap_ready" || status === "ready") return "success";
  if (isSceneBusy(status)) return "running";
  return "";
}

function metricNumber(
  metrics: Record<string, number | string> | undefined,
  key: string,
): number | undefined {
  const value = metrics?.[key];
  return typeof value === "number" ? value : undefined;
}

function metricString(
  metrics: Record<string, number | string> | undefined,
  key: string,
): string | undefined {
  const value = metrics?.[key];
  return typeof value === "string" ? value : undefined;
}

function formatPercent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "Unknown";
  return value.toLocaleString(undefined, { style: "percent", maximumFractionDigits: 0 });
}

function formatBytes(bytes: number | undefined): string {
  if (!bytes) return "Unknown";
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function externalSplatName(item: ExternalSplat): string {
  return item.source_label || "Imported scan";
}

interface SceneDetailProps {
  sceneId?: string;
  embedded?: boolean;
  onClose?: () => void;
  /** Hide technical labels and panels for non-technical users. */
  friendlyMode?: boolean;
}

export default function SceneDetail({
  sceneId: sceneIdProp,
  embedded,
  onClose,
  friendlyMode = false,
}: SceneDetailProps = {}) {
  const { sceneId: routeSceneId } = useParams<{ sceneId: string }>();
  const sceneId = sceneIdProp ?? routeSceneId;
  const navigate = useNavigate();
  const [meta, setMeta] = useState<SceneMetadata | null>(null);
  const [qa, setQa] = useState<QaReport | null>(null);
  const [qaProgress, setQaProgress] = useState<QaProgress | null>(null);
  const [colmap, setColmap] = useState<ColmapReport | null>(null);
  const [recovery, setRecovery] = useState<RecoveryReport | null>(null);
  const [extractProgress, setExtractProgress] = useState<ProgressInfo | null>(null);
  const [colmapProgress, setColmapProgress] = useState<ProgressInfo | null>(null);
  const [recoveryProgress, setRecoveryProgress] = useState<ProgressInfo | null>(null);
  const [experimentalDeblur, setExperimentalDeblur] = useState(false);
  const [lingbotProgress, setLingbotProgress] = useState<ProgressInfo | null>(null);
  const [ppispProgress, setPpispProgress] = useState<ProgressInfo | null>(null);
  const [artifixerProgress, setArtifixerProgress] = useState<ProgressInfo | null>(null);
  const [trainProgress, setTrainProgress] = useState<ProgressInfo | null>(null);
  const [splatReadiness, setSplatReadiness] = useState<SplatReadiness | null>(null);
  const [tools, setTools] = useState<ToolStatus | null>(null);
  const [trainIterations, setTrainIterations] = useState(0);
  const [trainIterationsTouched, setTrainIterationsTouched] = useState(false);
  const [splatPreset, setSplatPreset] = useState<SplatPresetId>("balanced");
  const [splatPresetTouched, setSplatPresetTouched] = useState(false);
  const [qaPreset, setQaPreset] = useState<QaPresetId>(DEFAULT_QA_PRESET.id);
  const [reextractFps, setReextractFps] = useState(DEFAULT_QA_PRESET.fps);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [edit, setEdit] = useState<Partial<SceneMetadata>>({});
  const [previewTab, setPreviewTab] = useState<PreviewTab>("sparse");
  const [externalSplatLabel, setExternalSplatLabel] = useState("Imported scan");
  const [importingSplat, setImportingSplat] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [systemStats, setSystemStats] = useState<SystemStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [energy, setEnergy] = useState<EnergySummary | null>(null);
  const wasExtractingRef = useRef(false);

  const load = useCallback(async () => {
    if (!sceneId) return;
    try {
      const data = await getScene(sceneId);
      setMeta(data.metadata);
      setQa(data.qa_report);
      setQaProgress(data.qa_progress);
      setColmap(data.colmap_report);
      setRecovery(data.recovery_report);
      setExtractProgress(data.progress_extract ?? data.jobs?.extract_frames?.progress ?? null);
      setColmapProgress(data.progress_colmap ?? data.jobs?.colmap?.progress ?? data.progress);
      setRecoveryProgress(
        data.progress_recovery ?? data.jobs?.colmap_recovery?.progress ?? null,
      );
      setLingbotProgress(data.progress_lingbot ?? data.jobs?.lingbot_map?.progress ?? null);
      setPpispProgress(data.progress_ppisp ?? data.jobs?.ppisp?.progress ?? null);
      setArtifixerProgress(
        data.progress_artifixer ?? data.jobs?.nvidia_artifixer?.progress ?? null,
      );
      setTrainProgress(data.progress_train ?? data.jobs?.train_splat?.progress ?? null);
      setSplatReadiness(data.splat_readiness ?? null);
      setEnergy(data.energy ?? null);
      const loadedPreset = getQaPreset(data.metadata.extraction?.qa_preset);
      setQaPreset(loadedPreset.id);
      setReextractFps(data.metadata.extraction?.fps ?? loadedPreset.fps);
      setEdit({
        title: data.metadata.title,
        description: data.metadata.description,
        creator: data.metadata.creator,
        location: data.metadata.location,
        capture_date: data.metadata.capture_date,
        capture_device: data.metadata.capture_device,
        notes: data.metadata.notes,
        rights: data.metadata.rights,
      });
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  }, [sceneId]);

  useEffect(() => {
    load();
    getTools().then(setTools).catch(() => {});
  }, [load]);

  useEffect(() => {
    if (!tools?.gpu_profile) return;
    const preferredPreset: SplatPresetId = meta?.quality_flags?.low_confidence_splat_source
      ? "robust_salvage"
      : defaultSplatPresetForGpu(tools.gpu_profile);
    const nextPreset = splatPresetTouched ? splatPreset : preferredPreset;
    if (!splatPresetTouched) setSplatPreset(nextPreset);
    if (!trainIterationsTouched) {
      setTrainIterations(resolveSplatPresetSettings(nextPreset, tools.gpu_profile).iterations);
    }
  }, [meta?.quality_flags, splatPreset, splatPresetTouched, tools?.gpu_profile, trainIterationsTouched]);

  const jobActive = (status?: string) => status === "running" || status === "paused";

  const extractPaused = extractProgress?.status === "paused";
  const extractRunning =
    meta?.status === "extracting_frames" ||
    meta?.status === "created" ||
    jobActive(extractProgress?.status);
  const colmapPaused = colmapProgress?.status === "paused";
  const colmapRunning =
    meta?.status === "colmap_running" || jobActive(colmapProgress?.status);
  const recoveryPaused = recoveryProgress?.status === "paused";
  const recoveryRunning =
    meta?.status === "colmap_recovery_running" || jobActive(recoveryProgress?.status);
  const lingbotPaused = lingbotProgress?.status === "paused";
  const lingbotRunning = jobActive(lingbotProgress?.status);
  const ppispPaused = ppispProgress?.status === "paused";
  const ppispRunning = jobActive(ppispProgress?.status);
  const artifixerPaused = artifixerProgress?.status === "paused";
  const artifixerRunning = jobActive(artifixerProgress?.status);
  const trainPaused = trainProgress?.status === "paused";
  const trainRunning =
    meta?.status === "training" || jobActive(trainProgress?.status);
  const anyRunning =
    colmapRunning ||
    recoveryRunning ||
    lingbotRunning ||
    ppispRunning ||
    artifixerRunning ||
    trainRunning ||
    extractRunning;

  const refreshStats = useCallback(async () => {
    try {
      setSystemStats(await getSystemStats());
    } catch {
      /* sensors optional */
    } finally {
      setStatsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!anyRunning) {
      setSystemStats(null);
      return;
    }
    setStatsLoading(true);
    refreshStats();
    const id = setInterval(() => {
      load();
      refreshStats();
    }, 1500);
    return () => clearInterval(id);
  }, [anyRunning, load, refreshStats]);

  useEffect(() => {
    if (wasExtractingRef.current && !extractRunning) {
      setPreviewTab("sparse");
    }
    wasExtractingRef.current = extractRunning;
  }, [extractRunning]);

  const qaStageActive = extractRunning && extractProgress?.stage === "qa";

  useEffect(() => {
    if (!sceneId || !qaStageActive) return;
    const id = setInterval(() => load(), 1500);
    return () => clearInterval(id);
  }, [sceneId, qaStageActive, load]);

  useEffect(() => {
    if (!meta || extractRunning) return;
    const sparseReady = !!(
      meta.outputs?.sparse_preview ||
      meta.status === "colmap_ready" ||
      meta.status === "ready" ||
      colmapProgress?.preview
    );
    if (sparseReady) setPreviewTab("sparse");
  }, [meta, extractRunning, colmapProgress?.preview]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!sceneId) return;
    setSaving(true);
    try {
      setMeta(await updateMetadata(sceneId, edit));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleReextract() {
    if (!sceneId) return;
    const preset = getQaPreset(qaPreset);
    await extractFrames(sceneId, reextractFps, true, {
      qaPreset,
      blurThreshold: preset.blurThreshold,
      duplicateThreshold: preset.duplicateThreshold,
    });
    load();
  }

  function handleQaPresetChange(nextPreset: QaPresetId) {
    const preset = getQaPreset(nextPreset);
    setQaPreset(nextPreset);
    setReextractFps(preset.fps);
  }

  async function handleRunColmap() {
    if (!sceneId) return;
    try {
      await runColmap(sceneId);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "COLMAP failed to start");
    }
  }

  async function handleRecoverColmap(force = false) {
    if (!sceneId) return;
    try {
      await recoverColmap(sceneId, { experimentalDeblur, force });
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "COLMAP recovery failed to start");
    }
  }

  async function handleImportSplat(file: File | null | undefined) {
    if (!sceneId || !file) return;
    setImportingSplat(true);
    try {
      const result = await importExternalSplat(sceneId, file, externalSplatLabel);
      setMeta(result.metadata);
      setExternalSplatLabel("Imported scan");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Imported scan could not be added");
    } finally {
      setImportingSplat(false);
    }
  }

  async function handleActiveSplat(source: "native" | "external", id?: string) {
    if (!sceneId) return;
    try {
      setMeta(await setActiveSplat(sceneId, source, id));
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Preview source could not be changed");
    }
  }

  async function handleTrainSplat() {
    if (!sceneId) return;
    try {
      const resolved = resolveSplatPresetSettings(splatPreset, tools?.gpu_profile);
      await trainSplat(sceneId, {
        preset: splatPreset,
        iterations: trainIterationsTouched ? trainIterations : resolved.iterations,
        downscaleFactor: resolved.downscaleFactor,
      });
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Training failed to start");
    }
  }

  function handleSplatPresetChange(nextPreset: SplatPresetId) {
    setSplatPreset(nextPreset);
    setSplatPresetTouched(true);
    setTrainIterationsTouched(false);
    setTrainIterations(resolveSplatPresetSettings(nextPreset, tools?.gpu_profile).iterations);
  }

  async function handleDelete() {
    if (!sceneId) return;
    setDeleting(true);
    try {
      await deleteScene(sceneId);
      if (embedded && onClose) onClose();
      else navigate("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
      setDeleting(false);
      setShowDelete(false);
    }
  }

  if (!sceneId) return null;
  if (error && !meta) return <p className="error-text">{error}</p>;
  if (!meta) return <p className="muted">Loading…</p>;

  const colmapAvailable = tools?.colmap.available ?? true;
  const hasSparsePreview = !!(
    meta.outputs?.sparse_preview ||
    meta.status === "colmap_ready" ||
    meta.status === "ready" ||
    colmapProgress?.preview
  );
  const hasFrames = !!meta.extraction?.frame_count;
  const hasContact = hasFrames;
  const hasLingbot = !!meta.outputs?.lingbot_preview;
  const busy = isSceneBusy(meta.status);
  const cacheBust = meta.updated_at;
  const sparseUrl = sparsePreviewUrl(sceneId) + `?t=${cacheBust}`;
  const latestExtractFrame = extractProgress?.preview;
  const extractionPreviewSrc = latestExtractFrame
    ? frameUrl(sceneId, latestExtractFrame.replace(/^frames\//, "")) +
      `?t=${encodeURIComponent(extractProgress?.updated_at ?? String(Date.now()))}`
    : null;
  const showQaSwipe = qaStageActive;
  const showExtractionBackdrop = extractRunning && !showQaSwipe;
  const qaMetrics = extractProgress?.metrics;
  const qaLiveFrame =
    metricString(qaMetrics, "qa_frame") ??
    extractProgress?.preview?.replace(/^frames\//, "");
  const qaLiveEntry = qaProgress?.frames?.find((f) => f.name === qaLiveFrame);
  const qaDecision = metricString(qaMetrics, "qa_decision");
  const externalSplats = meta.external_splats ?? [];
  const nativeSplatPath = meta.outputs?.splat || meta.splat?.path || "";
  const activeExternal =
    externalSplats.find((item) => item.active) ??
    externalSplats.find((item) => meta.outputs?.active_splat_preview === item.path) ??
    externalSplats[0];
  const activeSplatSource =
    meta.active_splat_source === "external" && activeExternal
      ? "external"
      : nativeSplatPath
        ? "native"
        : activeExternal
          ? "external"
          : "native";
  const activeSplatPath =
    activeSplatSource === "external" && activeExternal
      ? activeExternal.path
      : nativeSplatPath;
  const activeSplatUrl = activeSplatPath ? splatPathUrl(sceneId, activeSplatPath) + `?t=${cacheBust}` : "";
  const activeSplatLabel =
    activeSplatSource === "external" && activeExternal
      ? `${externalSplatName(activeExternal)} - imported preview`
      : "ArchiveSpace-generated local output";
  const hasAnySplatPreview = !!activeSplatPath;
  const blurRate = qa?.frame_count ? qa.blur.blurry_frame_count / qa.frame_count : 0;
  const registrationRatio =
    colmap?.registration_ratio ??
    meta.colmap?.registration_ratio ??
    (meta.colmap ? meta.colmap.registered_images / Math.max(1, meta.colmap.total_images) : undefined);
  const tabs = (
    [
      { id: "sparse" as const, label: "3D Scene Viewer", show: !!(hasSparsePreview || meta.status !== "ready") },
      { id: "transform" as const, label: "Alignment", show: !!(hasSparsePreview || hasAnySplatPreview) },
      { id: "alignment" as const, label: "Camera tracking", show: hasFrames || colmapRunning || !!meta.colmap },
      { id: "contact" as const, label: "Contact sheet", show: hasContact },
      { id: "lingbot" as const, label: "LingBot preview", show: hasLingbot },
    ] satisfies { id: PreviewTab; label: string; show: boolean }[]
  ).filter((t) => t.show);

  return (
    <div
      className={`scene-detail ${showExtractionBackdrop || showQaSwipe ? "is-extracting" : ""} ${showQaSwipe ? "is-qa-review" : ""}`}
    >
      {showExtractionBackdrop && (
        <ExtractionBackdrop
          src={extractionPreviewSrc}
          frameCount={metricNumber(extractProgress?.metrics, "frame_count")}
          expected={metricNumber(extractProgress?.metrics, "expected_frames")}
          fps={metricNumber(extractProgress?.metrics, "fps")}
          paused={extractPaused}
        />
      )}

      <div className="scene-detail-content">
      {!embedded && (
        <div className="detail-nav">
          <Link to="/" className="muted back-link">← Scenes</Link>
          <div className="detail-nav-actions">
            <button
              type="button"
              className="danger-text"
              disabled={busy}
              onClick={() => setShowDelete(true)}
            >
              Delete scene
            </button>
          </div>
        </div>
      )}

      <div className={`page-title page-title-row ${embedded ? "page-title--embedded" : ""}`}>
        <div className="page-title-main">
          {!embedded && <h1>{meta.title}</h1>}
          <p className={embedded ? "embedded-scene-status" : undefined}>
            {embedded ? <strong className="embedded-scene-title">{meta.title}</strong> : null}
            <span className={`badge ${statusBadgeClass(meta.status)}`}>
              {friendlyMode ? friendlyStatus(meta.status) : formatStatus(meta.status)}
            </span>
            {!embedded && !friendlyMode ? <span className="muted scene-id-inline">{sceneId}</span> : null}
          </p>
        </div>
        {(anyRunning || energy?.cost_pence || meta.energy_cost?.cost_pence) ? (
          <EnergyCostPanel
            stats={systemStats}
            energy={energy}
            sceneEnergy={meta.energy_cost}
            live={anyRunning}
            loading={statsLoading && !systemStats}
          />
        ) : null}
        {embedded ? (
          <button
            type="button"
            className="danger-text"
            disabled={busy}
            onClick={() => setShowDelete(true)}
          >
            Delete
          </button>
        ) : null}
      </div>

      {friendlyMode ? (
        <FriendlyStatusMessage status={meta.status} className="card" />
      ) : (
        <PipelineTrack
          meta={meta}
          flags={{
            extractRunning,
            colmapRunning,
            recoveryRunning,
            trainRunning,
          }}
          detail={
            extractProgress?.message ??
            colmapProgress?.message ??
            recoveryProgress?.message ??
            trainProgress?.message
          }
        />
      )}

      {anyRunning && !friendlyMode && (
        <SystemStatsBar
          stats={systemStats}
          loading={statsLoading && !systemStats}
        />
      )}

      {showQaSwipe && sceneId && (
        <div className="qa-stage-hero">
          {extractRunning && (
            <div className="qa-stage-panel">
              <FrameExtractionPanel
                sceneId={sceneId}
                progress={extractProgress}
                running={extractRunning && !extractPaused}
                paused={extractPaused}
                onJobControl={load}
              />
            </div>
          )}
          <QaSwipeReview
            sceneId={sceneId}
            liveFrame={qaLiveFrame}
            liveBlurScore={qaLiveEntry?.blur_score ?? metricNumber(qaMetrics, "qa_blur_score")}
            liveDuplicate={qaLiveEntry?.duplicate ?? false}
            liveDecision={qaDecision === "remove" || qaDecision === "keep" ? qaDecision : undefined}
            cacheBust={qaProgress?.updated_at ?? extractProgress?.updated_at}
            analyzed={qaProgress?.analyzed ?? metricNumber(qaMetrics, "qa_index")}
            total={metricNumber(qaMetrics, "frame_count")}
          />
        </div>
      )}

      {error && <p className="error-text">{error}</p>}

      {extractRunning && sceneId && !showQaSwipe && (
        <FrameExtractionPanel
          sceneId={sceneId}
          progress={extractProgress}
          running={extractRunning && !extractPaused}
          paused={extractPaused}
          onJobControl={load}
        />
      )}

      {colmapRunning && sceneId && (
        <ProcessingPanel
          title="COLMAP structure-from-motion"
          progress={colmapProgress}
          running={colmapRunning && !colmapPaused}
          paused={colmapPaused}
          sceneId={sceneId}
          jobType="colmap"
          onJobControl={load}
          stages={["Feature extraction", "Feature matching", "Sparse reconstruction", "Export & preview"]}
        />
      )}

      {recoveryRunning && sceneId && (
        <ProcessingPanel
          title="COLMAP recovery (blur clean-up & multi-FPS retry)"
          progress={recoveryProgress}
          running={recoveryRunning && !recoveryPaused}
          paused={recoveryPaused}
          sceneId={sceneId}
          jobType="colmap_recovery"
          onJobControl={load}
          stages={[
            "Prepare",
            "Re-extract real frames",
            "Blur & duplicate analysis",
            "Sequential COLMAP attempts",
            "Select best result",
          ]}
        />
      )}

      {meta.status === "needs_rescan" && (
        <div className="card rescan-panel">
          <h2>Needs rescan</h2>
          <p className="warning-text">
            All recovery attempts stayed below 40% registration. A fresh capture is required —
            no synthetic or generated viewpoints were used.
          </p>
          {(meta.rescan_advice ?? recovery?.rescan_advice ?? []).length > 0 && (
            <ul className="rescan-advice-list">
              {(meta.rescan_advice ?? recovery?.rescan_advice ?? []).map((tip, i) => (
                <li key={i}>{tip}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {trainRunning && sceneId && (
        <ProcessingPanel
          title="Gaussian splat training (Splatfacto)"
          progress={trainProgress}
          running={trainRunning && !trainPaused}
          paused={trainPaused}
          sceneId={sceneId}
          jobType="train_splat"
          onJobControl={load}
          stages={["Prepare dataset", "Train splat", "Export PLY", "Complete"]}
        />
      )}

      {lingbotRunning && sceneId && (
        <ProcessingPanel
          title="LingBot-Map fast preview (experimental)"
          progress={lingbotProgress}
          running={lingbotRunning && !lingbotPaused}
          paused={lingbotPaused}
          sceneId={sceneId}
          jobType="lingbot_map"
          onJobControl={load}
        />
      )}

      {ppispRunning && sceneId && (
        <ProcessingPanel
          title="PPiSP training handoff (experimental)"
          progress={ppispProgress}
          running={ppispRunning && !ppispPaused}
          paused={ppispPaused}
          sceneId={sceneId}
          jobType="ppisp"
          onJobControl={load}
          stages={["Prepare frames", "Validate runtime", "Write manifest"]}
        />
      )}

      {artifixerRunning && sceneId && (
        <ProcessingPanel
          title="NVIDIA ArtiFixer handoff (experimental)"
          progress={artifixerProgress}
          running={artifixerRunning && !artifixerPaused}
          paused={artifixerPaused}
          sceneId={sceneId}
          jobType="nvidia_artifixer"
          onJobControl={load}
          stages={["COLMAP handoff", "Runtime validation", "Integration manifest", "Complete"]}
        />
      )}

      {tools && !colmapAvailable && (
        <div className="card alert-card">
          <strong>COLMAP not detected</strong>
          <p className="muted">Run <code>.\scripts\install_colmap.ps1</code></p>
        </div>
      )}

      {meta.last_error && meta.status.includes("failed") && (
        <div className="card error-card">
          <strong>Processing error</strong>
          <pre className="error-pre">{meta.last_error}</pre>
        </div>
      )}

      <div className="scene-detail-body">
      <div className="scene-detail-layout">
      <div className="scene-detail-preview">
      {hasAnySplatPreview && (
        <div className="card preview-card">
          <div className="splat-source-header">
            <div>
              <p className="workspace-kicker">3D preview</p>
              <h2>{activeSplatSource === "external" ? "Imported scan preview" : "ArchiveSpace scan preview"}</h2>
            </div>
            <div className="splat-source-switch" role="tablist" aria-label="3D preview source">
              {nativeSplatPath && (
                <button
                  type="button"
                  className={activeSplatSource === "native" ? "active" : ""}
                  aria-selected={activeSplatSource === "native"}
                  onClick={() => handleActiveSplat("native")}
                >
                  ArchiveSpace
                </button>
              )}
              {externalSplats.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={activeSplatSource === "external" && activeExternal?.id === item.id ? "active" : ""}
                  aria-selected={activeSplatSource === "external" && activeExternal?.id === item.id}
                  onClick={() => handleActiveSplat("external", item.id)}
                >
                  {externalSplatName(item)}
                </button>
              ))}
            </div>
          </div>
          <SplatViewer
            sceneId={sceneId}
            title="3D scan viewer"
            sourceLabel={activeSplatLabel}
            sourceUrl={activeSplatUrl}
            sceneTransform={meta.sceneTransform}
          />
          {activeSplatSource === "external" ? (
            <p className="muted text-sm btn-spaced-sm">
              This is an imported preview from another tool. It helps comparison, but it is not the native ArchiveSpace preservation output.
            </p>
          ) : null}
        </div>
      )}

      {tabs.length > 0 && (
        <div className="card preview-card">
          <div className="preview-tabs" role="tablist">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={previewTab === tab.id}
                className={`preview-tab ${previewTab === tab.id ? "active" : ""}`}
                onClick={() => setPreviewTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {previewTab === "sparse" && (hasSparsePreview || meta.status !== "ready") && (
            <SparsePointViewer
              sceneId={sceneId}
              fallbackImageUrl={hasSparsePreview ? sparseUrl : undefined}
              sparseReady={hasSparsePreview}
              processing={colmapRunning || colmapProgress?.status === "running"}
              sceneTransform={meta.sceneTransform}
            />
          )}

          {previewTab === "transform" && (
            <SceneAlignmentPanel
              sceneId={sceneId}
              metadata={meta}
              onSaved={(next) => {
                setMeta(next);
                setPreviewTab("sparse");
              }}
            />
          )}

          {previewTab === "alignment" && (
            <AlignmentProcessPanel
              sceneId={sceneId}
              cacheBust={cacheBust}
              progress={colmapProgress}
              colmap={colmap}
              status={meta.status}
            />
          )}

          {previewTab === "contact" && hasContact && (
            <ContactSheetGallery sceneId={sceneId} cacheBust={cacheBust} />
          )}

          {previewTab === "lingbot" && hasLingbot && meta.outputs.lingbot_preview && (
            <div className="preview-viewer">
              {meta.outputs.lingbot_preview.endsWith(".mp4") ? (
                <video
                  controls
                  className="preview-video"
                  src={derivativeUrl(sceneId, meta.outputs.lingbot_preview.replace("derivatives/", ""))}
                />
              ) : (
                <img
                  src={derivativeUrl(sceneId, meta.outputs.lingbot_preview.replace("derivatives/", ""))}
                  alt="LingBot preview"
                  className="preview-image"
                />
              )}
            </div>
          )}
        </div>
      )}
      </div>

      <div className="scene-detail-sidebar">
        <div className="card metadata-card">
          <h2>Metadata</h2>
          <form className="metadata-form" onSubmit={handleSave}>
            {(
              [
                ["title", "Title"],
                ["creator", "Artist / creator"],
                ["location", "Location"],
                ["capture_date", "Date captured"],
                ["capture_device", "Capture device"],
              ] as const
            ).map(([key, label]) => (
              <div className="field" key={key}>
                <label>{label}</label>
                <input
                  value={(edit[key] as string) ?? ""}
                  onChange={(e) => setEdit({ ...edit, [key]: e.target.value })}
                />
              </div>
            ))}
            <div className="field field--full">
              <label>Description</label>
              <textarea rows={2} value={edit.description ?? ""} onChange={(e) => setEdit({ ...edit, description: e.target.value })} />
            </div>
            <div className="field field--full">
              <label>Notes</label>
              <textarea rows={2} value={edit.notes ?? ""} onChange={(e) => setEdit({ ...edit, notes: e.target.value })} />
            </div>
            <div className="metadata-form-actions field--full">
              <button type="submit" disabled={saving}>{saving ? "Saving…" : "Save metadata"}</button>
            </div>
          </form>
        </div>

        <div className="stats-grid">
          {!friendlyMode && (
          <div className="card">
            <h2>Pipeline</h2>
            <ul className="stat-list">
              <li><span>FFmpeg</span><strong>{meta.processing_pipeline.ffmpeg ? "✓" : "—"}</strong></li>
              <li><span>COLMAP</span><strong>{meta.processing_pipeline.colmap ? "✓" : "—"}</strong></li>
              <li><span>LingBot-Map</span><strong>{meta.branches?.lingbot_map?.status ?? "—"}</strong></li>
              <li><span>PPiSP</span><strong>{meta.branches?.ppisp?.status ?? "—"}</strong></li>
              <li><span>ArtiFixer</span><strong>{meta.branches?.nvidia_artifixer?.status ?? "—"}</strong></li>
              <li><span>Trainer</span><strong>{meta.processing_pipeline.trainer || "—"}</strong></li>
            </ul>
          </div>
          )}

          {!friendlyMode && (energy?.cost_pence || meta.energy_cost?.cost_pence) ? (
            <div className="card">
              <h2>Energy cost</h2>
              <ul className="stat-list">
                <li>
                  <span>Scene total</span>
                  <strong>
                    {formatEnergyCost(energy?.cost_pence ?? meta.energy_cost?.cost_pence ?? 0)}
                  </strong>
                </li>
                <li>
                  <span>Energy used</span>
                  <strong>{(energy?.energy_wh ?? meta.energy_cost?.energy_wh ?? 0).toFixed(2)} Wh</strong>
                </li>
                <li>
                  <span>Rate</span>
                  <strong>{energy?.rate_pence_per_kwh ?? meta.energy_cost?.rate_pence_per_kwh ?? 24.67}p/kWh</strong>
                </li>
              </ul>
              {energy?.jobs && Object.keys(energy.jobs).length > 0 && (
                <ul className="stat-list energy-job-list">
                  {Object.entries(energy.jobs).map(([job, summary]) => (
                    <li key={job}>
                      <span>{job.replace(/_/g, " ")}</span>
                      <strong>
                        {formatEnergyCost(summary.cost_pence)} · {summary.energy_wh.toFixed(2)} Wh
                      </strong>
                    </li>
                  ))}
                </ul>
              )}
              {energy?.log && energy.log.length > 0 && (
                <details className="log-details">
                  <summary>Energy log</summary>
                  <pre className="log-tail">
                    {energy.log.map((entry) => entry.message).join("\n")}
                  </pre>
                </details>
              )}
            </div>
          ) : null}

          <div className="card">
            <h2>Frame extraction</h2>
            {meta.extraction ? (
              <ul className="stat-list">
                <li><span>Frames</span><strong>{meta.extraction.frame_count}</strong></li>
                <li><span>FPS</span><strong>{meta.extraction.fps}</strong></li>
                <li><span>QA preset</span><strong>{getQaPreset(meta.extraction.qa_preset).label}</strong></li>
                <li><span>Source</span><strong>{meta.source_filename}</strong></li>
              </ul>
            ) : (
              <p className="muted">Not extracted yet.</p>
            )}
            <div className="field field-spaced">
              <label htmlFor="scene-qa-preset">QA preset for re-run</label>
              <select
                id="scene-qa-preset"
                value={qaPreset}
                onChange={(e) => handleQaPresetChange(e.target.value as QaPresetId)}
                disabled={busy}
              >
                {QA_PRESETS.map((preset) => (
                  <option key={preset.id} value={preset.id}>
                    {preset.label}
                  </option>
                ))}
              </select>
              <p className="muted field-hint">
                {getQaPreset(qaPreset).description} Blur {getQaPreset(qaPreset).blurThreshold}, duplicate{" "}
                {getQaPreset(qaPreset).duplicateThreshold}.
              </p>
            </div>
            <div className="field">
              <label htmlFor="scene-reextract-fps">Re-run FPS</label>
              <input
                id="scene-reextract-fps"
                type="number"
                min={0.5}
                max={30}
                step={0.5}
                value={reextractFps}
                onChange={(e) => setReextractFps(parseFloat(e.target.value))}
                disabled={busy}
              />
            </div>
            <button type="button" onClick={handleReextract} disabled={busy} className="btn-spaced">
              Re-run extraction
            </button>
          </div>

          <div className="card">
            <h2>COLMAP results</h2>
            {meta.colmap ? (
              <ul className="stat-list">
                <li><span>Registered</span><strong>{meta.colmap.registered_images} / {meta.colmap.total_images}</strong></li>
                <li>
                  <span>Registration</span>
                  <strong>
                    {(
                      colmap?.registration_ratio ??
                      meta.colmap.registration_ratio ??
                      meta.colmap.registered_images / Math.max(1, meta.colmap.total_images)
                    ).toLocaleString(undefined, { style: "percent", maximumFractionDigits: 0 })}
                  </strong>
                </li>
                <li><span>Sparse points</span><strong>{meta.colmap.point_count.toLocaleString()}</strong></li>
                {(colmap?.mean_reprojection_error ?? meta.colmap.mean_reprojection_error) != null && (
                  <li>
                    <span>Reprojection err.</span>
                    <strong>
                      {(colmap?.mean_reprojection_error ?? meta.colmap.mean_reprojection_error)!.toFixed(2)} px
                    </strong>
                  </li>
                )}
              </ul>
            ) : colmap ? (
              <ul className="stat-list">
                <li><span>Registered</span><strong>{colmap.registered_images} / {colmap.total_images}</strong></li>
                <li>
                  <span>Registration</span>
                  <strong>{colmap.registration_ratio.toLocaleString(undefined, { style: "percent", maximumFractionDigits: 0 })}</strong>
                </li>
                <li><span>Sparse points</span><strong>{colmap.point_count.toLocaleString()}</strong></li>
              </ul>
            ) : (
              <p className="muted">{meta.extraction?.frame_count ? "Ready to run." : "Extract frames first."}</p>
            )}
            {colmap?.warnings?.map((w, i) => <p key={i} className="warning-text">{w}</p>)}
            {(colmap?.registration_ratio ?? 1) < 0.6 && meta.status !== "needs_rescan" && !recoveryRunning && (
              <p className="muted text-sm btn-spaced-sm">
                Registration is below 60%. Recovery will analyse blur, remove near-duplicates,
                and retry COLMAP at 2 / 5 / 10 FPS with sequential matching.
              </p>
            )}
            {recovery && (
              <details className="log-details btn-spaced-sm">
                <summary>Recovery report ({recovery.best_attempt_id})</summary>
                <ul className="stat-list">
                  <li><span>Initial ratio</span><strong>{(recovery.initial_registration_ratio * 100).toFixed(0)}%</strong></li>
                  <li><span>Best ratio</span><strong>{(recovery.best_registration_ratio * 100).toFixed(0)}%</strong></li>
                  {recovery.best_mean_reprojection_error != null && (
                    <li><span>Best reproj.</span><strong>{recovery.best_mean_reprojection_error.toFixed(2)} px</strong></li>
                  )}
                </ul>
                {recovery.attempts?.length > 0 && (
                  <pre className="log-tail">
                    {recovery.attempts.map((a) =>
                      `${a.id}: ${((a.registration_ratio ?? 0) * 100).toFixed(0)}%`
                      + (a.mean_reprojection_error != null ? ` · ${a.mean_reprojection_error.toFixed(2)}px` : "")
                      + (a.experimental ? " (experimental)" : ""),
                    ).join("\n")}
                  </pre>
                )}
              </details>
            )}
            <button
              type="button"
              onClick={handleRunColmap}
              disabled={!colmapAvailable || !meta.extraction?.frame_count || colmapRunning || recoveryRunning}
              className="primary btn-spaced"
            >
              {colmapRunning ? "COLMAP running…" : "Run COLMAP"}
            </button>
            {(colmap?.registration_ratio ?? 1) < 0.6 && (
              <div className="recovery-actions btn-spaced-sm">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={experimentalDeblur}
                    onChange={(e) => setExperimentalDeblur(e.target.checked)}
                  />
                  Experimental deblur (real frames only, non-master)
                </label>
                <button
                  type="button"
                  onClick={() => handleRecoverColmap(false)}
                  disabled={colmapRunning || recoveryRunning}
                  className="btn-spaced-sm"
                >
                  {recoveryRunning ? "Recovery running…" : "Run COLMAP recovery"}
                </button>
              </div>
            )}
          </div>

          <div className="card">
            <h2>3D scan output</h2>
            {hasAnySplatPreview && (
              <ul className="stat-list">
                <li>
                  <span>Previewing</span>
                  <strong>{activeSplatSource === "external" && activeExternal ? externalSplatName(activeExternal) : "ArchiveSpace scan"}</strong>
                </li>
                <li>
                  <span>Source type</span>
                  <strong>{activeSplatSource === "external" ? "Imported comparison" : "Native ArchiveSpace output"}</strong>
                </li>
                {activeSplatSource === "external" && activeExternal && (
                  <li><span>Imported size</span><strong>{formatBytes(activeExternal.size_bytes)}</strong></li>
                )}
              </ul>
            )}
            {meta.splat ? (
              <ul className="stat-list">
                <li><span>ArchiveSpace file</span><strong>{meta.splat.path}</strong></li>
                <li><span>Iterations</span><strong>{meta.splat.iterations.toLocaleString()}</strong></li>
                {meta.splat.training_preset && (
                  <li><span>Preset</span><strong>{getSplatPreset(meta.splat.training_preset).label}</strong></li>
                )}
                {meta.splat.downscale_factor && (
                  <li><span>Downscale</span><strong>{meta.splat.downscale_factor}×</strong></li>
                )}
                <li><span>Size</span><strong>{(meta.splat.size_bytes / 1024 / 1024).toFixed(1)} MB</strong></li>
              </ul>
            ) : (
              <p className="muted">
                {meta.colmap?.success || meta.status === "colmap_ready"
                  ? "The scan is ready for a local 3D output."
                  : externalSplats.length
                    ? "No ArchiveSpace 3D output yet. Imported scans can still be previewed."
                    : "Finish camera matching first, or import a scan from another tool."}
              </p>
            )}
            {nativeSplatPath && (
              <div className="native-quality-facts btn-spaced-sm">
                <p className="workspace-kicker">ArchiveSpace scan facts</p>
                <ul className="stat-list">
                  <li><span>Blur rate</span><strong>{qa ? formatPercent(blurRate) : "Unknown"}</strong></li>
                  <li><span>Matched camera positions</span><strong>{formatPercent(registrationRatio)}</strong></li>
                  <li>
                    <span>Sparse points</span>
                    <strong>{(meta.colmap?.point_count ?? colmap?.point_count ?? 0).toLocaleString()}</strong>
                  </li>
                  <li>
                    <span>Training mode</span>
                    <strong>{meta.splat?.training_preset ? getSplatPreset(meta.splat.training_preset).label : "Not trained yet"}</strong>
                  </li>
                  {(meta.colmap?.mean_reprojection_error ?? colmap?.mean_reprojection_error) != null && (
                    <li>
                      <span>Matching error</span>
                      <strong>{(meta.colmap?.mean_reprojection_error ?? colmap?.mean_reprojection_error)!.toFixed(2)} px</strong>
                    </li>
                  )}
                </ul>
              </div>
            )}
            {splatReadiness && !splatReadiness.ready && (
              <p className="muted text-sm btn-spaced-sm error-text">
                {splatReadiness.blockers.join(" ")}
              </p>
            )}
            {meta.quality_flags?.low_confidence_splat_source && (
              <p className="muted text-sm btn-spaced-sm warning-text">
                Low-confidence source: {meta.quality_flags.low_confidence_splat_source.reason}
              </p>
            )}
            {tools && !tools.splat_training?.available && (
              <p className="muted text-sm btn-spaced-sm">
                Training env not configured. Run <code>.\scripts\install_train_env.ps1</code> and set <code>VITRINE_TRAIN_PYTHON</code>.
              </p>
            )}
            {tools?.gpu_profile?.note && (
              <p className="muted text-sm btn-spaced-sm">{tools.gpu_profile.note}</p>
            )}
            <div className="external-splat-import btn-spaced">
              <label htmlFor="external-splat-label">Import label</label>
              <input
                id="external-splat-label"
                value={externalSplatLabel}
                onChange={(e) => setExternalSplatLabel(e.target.value)}
                placeholder="Luma scan"
              />
              <label className="file-input-label">
                {importingSplat ? "Adding imported scan..." : "Add imported scan"}
                <input
                  type="file"
                  accept=".ply,.splat,.ksplat"
                  disabled={importingSplat}
                  onChange={(e) => {
                    void handleImportSplat(e.target.files?.[0]);
                    e.currentTarget.value = "";
                  }}
                />
              </label>
              <p className="muted field-hint">
                Imports from Luma, Polycam, or similar tools are saved as comparison previews, not ArchiveSpace evidence.
              </p>
            </div>
            <div className="field field-spaced">
              <label htmlFor="splat-preset">Local output quality</label>
              <select
                id="splat-preset"
                value={splatPreset}
                onChange={(e) => handleSplatPresetChange(e.target.value as SplatPresetId)}
                disabled={trainRunning}
              >
                {SPLAT_PRESETS.map((preset) => (
                  <option key={preset.id} value={preset.id}>
                    {preset.label}
                  </option>
                ))}
              </select>
              <p className="muted field-hint">
                {getSplatPreset(splatPreset).description}{" "}
                {(() => {
                  const resolved = resolveSplatPresetSettings(splatPreset, tools?.gpu_profile);
                  return `${resolved.iterations.toLocaleString()} iterations · ${resolved.downscaleFactor}× downscale`;
                })()}
              </p>
            </div>
            <div className="field field-spaced">
              <label>Advanced training steps</label>
              <input
                type="number"
                min={5000}
                max={100000}
                step={5000}
                value={trainIterations}
                onChange={(e) => {
                  setTrainIterationsTouched(true);
                  setTrainIterations(parseInt(e.target.value, 10));
                }}
              />
            </div>
            <button
              type="button"
              onClick={handleTrainSplat}
              disabled={
                !tools?.splat_training?.available ||
                trainRunning ||
                !(splatReadiness?.ready ?? (meta.colmap?.success || meta.status === "colmap_ready"))
              }
              className="primary btn-spaced-sm"
            >
              {trainRunning
                ? "Creating..."
                : splatPreset === "fast_preview"
                  ? "Create quick 3D preview"
                  : "Create ArchiveSpace 3D scan"}
            </button>
          </div>

          {qa && (
            <div className="card">
              <h2>Frame QA</h2>
              <ul className="stat-list">
                <li><span>Resolution</span><strong>{qa.resolution.width}×{qa.resolution.height}</strong></li>
                <li><span>Blur avg</span><strong>{qa.blur.average}</strong></li>
                <li><span>QA passed</span><strong>{qa.passed ? "Yes" : "No"}</strong></li>
                <li><span>Preset</span><strong>{getQaPreset(qa.qa_preset).label}</strong></li>
              </ul>
            </div>
          )}
        </div>

        {!friendlyMode && <ExperimentalBranches sceneId={sceneId} onRefresh={load} />}
      </div>
      </div>
      </div>
      </div>

      <ConfirmDialog
        open={showDelete}
        title="Delete scene?"
        message={`Permanently remove "${meta.title}" and all associated data. This cannot be undone.`}
        confirmLabel="Delete permanently"
        danger
        busy={deleting}
        onConfirm={handleDelete}
        onCancel={() => !deleting && setShowDelete(false)}
      />
    </div>
  );
}
