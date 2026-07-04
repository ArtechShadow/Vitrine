// Create-archive wizard with shareable URL state (?source=&step=&scene=).
//
// Harvested from PR #6's CreateArchiveWizard but re-shaped for OUR job-centric
// backend: uploading a capture *starts the whole pipeline* (see app.py /upload
// → start_pipeline), so there are no separate extract/colmap/train buttons.
// The later steps observe the single run over SSE. Steps:
//   1 upload → 2 review → 3 quality → 4 build → 5 view → 6 export

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  getScene,
  importGoogleDrive,
  uploadImages,
  uploadVideo,
  uploadZip,
  exportUrl,
  type DriveContentType,
  type SceneDetail,
  type SourceType,
} from "../api/client";
import { isSceneBusy, isSceneReady } from "../lib/friendlyStatus";
import { formatBytes } from "../lib/format";
import { QA_PRESETS, DEFAULT_QA_PRESET } from "../lib/qaPresets";
import ProgressPanel from "../components/ProgressPanel";
import SplatViewer from "../components/SplatViewer";
import QaSwipeReview from "../components/QaSwipeReview";

const STEPS: readonly string[] = ["Add media", "Review", "Quality", "Build", "View", "Export"];

function parseSource(value: string | null): SourceType {
  if (value === "photos" || value === "images" || value === "folder") return "images";
  if (value === "zip") return "zip";
  if (value === "google_drive" || value === "drive") return "google_drive";
  return "video";
}

function WizardProgress({ current }: { current: number }) {
  return (
    <ol className="wizard-progress" aria-label="Wizard steps">
      {STEPS.map((label, i) => {
        const n = i + 1;
        const cls = n < current ? "done" : n === current ? "active" : "pending";
        return (
          <li key={label} className={`wizard-step ${cls}`}>
            <span className="wizard-step-num">{n}</span>
            <span className="wizard-step-label">{label}</span>
          </li>
        );
      })}
    </ol>
  );
}

export default function CreateArchiveWizard() {
  const [params, setParams] = useSearchParams();

  const source = parseSource(params.get("source"));
  const step = Math.min(STEPS.length, Math.max(1, parseInt(params.get("step") ?? "1", 10) || 1));
  const sceneId = params.get("scene");

  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [imageFiles, setImageFiles] = useState<File[]>([]);
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [driveUrl, setDriveUrl] = useState("");
  const [driveType, setDriveType] = useState<DriveContentType>("unknown");
  const [title, setTitle] = useState("");
  const [qaPreset, setQaPreset] = useState(DEFAULT_QA_PRESET.id);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<SceneDetail | null>(null);
  const detailTimer = useRef<number | null>(null);

  const goto = useCallback(
    (nextStep: number, nextScene?: string) => {
      const p = new URLSearchParams(params);
      p.set("source", source);
      p.set("step", String(nextStep));
      const scene = nextScene ?? sceneId;
      if (scene) p.set("scene", scene);
      setParams(p);
    },
    [params, source, sceneId, setParams],
  );

  // Load scene detail once a scene exists and we are past upload. Poll lightly
  // while busy so the review/quality steps reflect the running pipeline; the
  // build step's live progress comes from SSE inside ProgressPanel.
  useEffect(() => {
    if (!sceneId || step < 2) return;
    let active = true;
    const fetchDetail = () => {
      getScene(sceneId)
        .then((d) => active && setDetail(d))
        .catch(() => {});
    };
    fetchDetail();
    detailTimer.current = window.setInterval(() => {
      if (detail && !isSceneBusy(detail.metadata.status)) return;
      fetchDetail();
    }, 4000);
    return () => {
      active = false;
      if (detailTimer.current != null) window.clearInterval(detailTimer.current);
    };
    // Intentionally keyed on sceneId/step only; `detail` is read fresh each fetch.
  }, [sceneId, step]);

  const fileSummary = useMemo(() => {
    if (source === "video" && videoFile) return [`${videoFile.name} (${formatBytes(videoFile.size)})`];
    if (source === "zip" && zipFile) return [`${zipFile.name} (${formatBytes(zipFile.size)})`];
    if (source === "google_drive") return [driveUrl || "Google Drive link"];
    return imageFiles.map((f) => f.name);
  }, [source, videoFile, zipFile, imageFiles, driveUrl]);

  async function handleStart() {
    setBusy(true);
    setError(null);
    try {
      let created: { scene_id: string };
      if (source === "video") {
        if (!videoFile) throw new Error("Add a video first.");
        created = await uploadVideo(videoFile, title);
      } else if (source === "zip") {
        if (!zipFile) throw new Error("Add a folder or ZIP first.");
        created = await uploadZip(zipFile, title);
      } else if (source === "google_drive") {
        created = await importGoogleDrive(driveUrl, driveType, title);
      } else {
        if (imageFiles.length === 0) throw new Error("Add at least one photo.");
        created = await uploadImages(imageFiles, title);
      }
      if (!created.scene_id) throw new Error("The backend did not return a scene id.");
      goto(2, created.scene_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start");
    } finally {
      setBusy(false);
    }
  }

  const canStart =
    (source === "video" && !!videoFile) ||
    (source === "zip" && !!zipFile) ||
    (source === "google_drive" && driveUrl.trim().length > 10) ||
    (source === "images" && imageFiles.length > 0);

  const status = detail?.metadata.status ?? "";
  const ready = isSceneReady(status);

  return (
    <div className="page wizard-page">
      <header className="hero compact">
        <h1>Create archive</h1>
        <p className="muted">Add media, then Vitrine reconstructs a 3D scene locally.</p>
      </header>

      <WizardProgress current={step} />

      <div className="wizard-content card">
        {step === 1 && (
          <div className="wizard-panel">
            {source === "video" && (
              <label className="field">
                <span>Walkthrough video</span>
                <input
                  type="file"
                  accept="video/mp4,video/quicktime,video/x-msvideo,video/x-matroska,video/webm"
                  onChange={(e) => setVideoFile(e.target.files?.[0] ?? null)}
                />
                <small className="muted">Move slowly, cover every angle, avoid heavy motion blur.</small>
              </label>
            )}

            {source === "images" && (
              <label className="field">
                <span>Photos</span>
                <input type="file" accept="image/*" multiple onChange={(e) => setImageFiles(Array.from(e.target.files ?? []))} />
                <small className="muted">
                  {imageFiles.length > 0 ? `${imageFiles.length} selected` : "Stills give sharper reconstructions than video."}
                </small>
              </label>
            )}

            {source === "zip" && (
              <label className="field">
                <span>Folder or ZIP archive</span>
                <input type="file" accept=".zip,application/zip" onChange={(e) => setZipFile(e.target.files?.[0] ?? null)} />
                <small className="muted">A prepared image set packaged as a .zip.</small>
              </label>
            )}

            {source === "google_drive" && (
              <>
                <label className="field">
                  <span>Shared Google Drive link</span>
                  <input
                    type="url"
                    placeholder="https://drive.google.com/…"
                    value={driveUrl}
                    onChange={(e) => setDriveUrl(e.target.value)}
                  />
                  <small className="muted">A folder link prefers raw/still images; a file link is used as-is.</small>
                </label>
                <label className="field">
                  <span>What is in the link?</span>
                  <select value={driveType} onChange={(e) => setDriveType(e.target.value as DriveContentType)}>
                    <option value="unknown">Let Vitrine detect</option>
                    <option value="photos">Photos</option>
                    <option value="video">A video</option>
                    <option value="zip">A ZIP archive</option>
                  </select>
                </label>
              </>
            )}

            <label className="field">
              <span>Archive title (optional)</span>
              <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Gallery — east room" />
            </label>

            <label className="field">
              <span>Quality intent</span>
              <select value={qaPreset} onChange={(e) => setQaPreset(e.target.value)}>
                {QA_PRESETS.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label} — {p.description}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}

        {step === 2 && (
          <div className="wizard-panel">
            <h2>Review</h2>
            <p className="muted">Vitrine has copied your capture and started the pipeline.</p>
            <ul className="review-list">
              {fileSummary.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
            {detail && <p className="muted">Current status: {detail.metadata.status}</p>}
          </div>
        )}

        {step === 3 && sceneId && (
          <div className="wizard-panel">
            <h2>Quality check</h2>
            <p className="muted">Sharp, blurry, and duplicate frames as assessed by the capture-quality gate.</p>
            <QaSwipeReview sceneId={sceneId} qa={detail?.qa_report ?? null} />
          </div>
        )}

        {step === 4 && sceneId && (
          <div className="wizard-panel">
            <h2>Building your archive</h2>
            <ProgressPanel
              sceneId={sceneId}
              status={status}
              currentStage={detail?.metadata.current_stage}
              active={!ready}
              onDone={() => getScene(sceneId).then(setDetail).catch(() => {})}
            />
          </div>
        )}

        {step === 5 && sceneId && (
          <div className="wizard-panel">
            <h2>View scene</h2>
            {ready ? (
              <SplatViewer sceneId={sceneId} title={detail?.metadata.title} sceneTransform={detail?.metadata.sceneTransform} />
            ) : (
              <p className="muted">The 3D splat is not ready yet. Return to the Build step to watch progress.</p>
            )}
          </div>
        )}

        {step === 6 && sceneId && (
          <div className="wizard-panel">
            <h2>Export</h2>
            <p className="muted">Download everything this run produced as a single archive.</p>
            <a className="primary" href={exportUrl(sceneId)} download>
              Download run archive (.zip)
            </a>
          </div>
        )}
      </div>

      {error && <p className="error-text">{error}</p>}

      <div className="wizard-nav">
        {step > 1 && (
          <button type="button" className="secondary" onClick={() => goto(step - 1)}>
            Back
          </button>
        )}
        {step === 1 && (
          <button type="button" className="primary" disabled={!canStart || busy} onClick={handleStart}>
            {busy ? "Starting…" : "Continue"}
          </button>
        )}
        {step > 1 && step < STEPS.length && (
          <button type="button" className="primary" onClick={() => goto(step + 1)}>
            {step === 4 && !ready ? "Continue anyway" : "Next"}
          </button>
        )}
        {step === STEPS.length && sceneId && (
          <Link to={`/scenes/${sceneId}`} className="primary">
            Open full workspace
          </Link>
        )}
      </div>
    </div>
  );
}
