import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  createArchiveJob,
  importGoogleDriveLink,
  startArchiveBuild,
  uploadImages,
  uploadZip,
  type GoogleDriveContentType,
  type InputSource,
} from "../api/archiveService";
import { getScene, runColmap, trainSplat, extractFrames } from "../api/client";
import { useOnline } from "../context/OnlineContext";
import AdvancedSettingsPanel from "../components/AdvancedSettingsPanel";
import BackendStatusPanel from "../components/BackendStatusPanel";
import SceneAlignmentPanel from "../components/SceneAlignmentPanel";
import BatchImageUploadPanel from "../components/wizard/BatchImageUploadPanel";
import BuildArchiveStep from "../components/wizard/BuildArchiveStep";
import ExportStep from "../components/wizard/ExportStep";
import GoogleDriveImportPanel from "../components/wizard/GoogleDriveImportPanel";
import QualityCheckStep from "../components/wizard/QualityCheckStep";
import ReviewFilesStep from "../components/wizard/ReviewFilesStep";
import SceneViewerStep from "../components/wizard/SceneViewerStep";
import VideoUploadPanel from "../components/wizard/VideoUploadPanel";
import WizardProgress from "../components/wizard/WizardProgress";

function parseSource(value: string | null): InputSource {
  if (value === "photos" || value === "folder") return "photos";
  if (value === "zip") return "zip";
  if (value === "google_drive" || value === "drive") return "google_drive";
  return "video";
}

export default function CreateArchiveWizard() {
  const [params, setParams] = useSearchParams();
  const { online } = useOnline();

  const source = parseSource(params.get("source"));
  const step = Math.min(7, Math.max(1, parseInt(params.get("step") ?? "1", 10) || 1));
  const existingSceneId = params.get("scene");

  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [imageFiles, setImageFiles] = useState<File[]>([]);
  const [title, setTitle] = useState("");
  const [driveUrl, setDriveUrl] = useState("");
  const [driveType, setDriveType] = useState<GoogleDriveContentType>("unknown");
  const [sceneId, setSceneId] = useState<string | null>(existingSceneId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [qa, setQa] = useState<import("../api/client").QaReport | null>(null);
  const [colmap, setColmap] = useState<import("../api/client").ColmapReport | null>(null);
  const [metadata, setMetadata] = useState<import("../api/client").SceneMetadata | null>(null);
  const [qualityLoading, setQualityLoading] = useState(false);

  const fileNames = useMemo(() => {
    if (source === "video" && videoFile) return [videoFile.name];
    if (source === "google_drive") return [driveUrl || "Google Drive link"];
    return imageFiles.map((f) => f.name);
  }, [source, videoFile, imageFiles, driveUrl]);

  const totalSizeMb = useMemo(() => {
    const files = source === "video" && videoFile ? [videoFile] : imageFiles;
    return files.reduce((sum, f) => sum + f.size, 0) / 1024 / 1024;
  }, [source, videoFile, imageFiles]);

  const setStep = useCallback(
    (next: number) => {
      const p = new URLSearchParams(params);
      p.set("step", String(next));
      if (sceneId) p.set("scene", sceneId);
      setParams(p);
    },
    [params, sceneId, setParams],
  );

  useEffect(() => {
    if (!sceneId || step < 3) return;
    let active = true;
    setQualityLoading(true);
    getScene(sceneId)
      .then((d) => {
        if (!active) return;
        setQa(d.qa_report);
        setColmap(d.colmap_report);
        setMetadata(d.metadata);
      })
      .catch(() => {})
      .finally(() => {
        if (active) setQualityLoading(false);
      });
    return () => {
      active = false;
    };
  }, [sceneId, step]);

  async function handleStartFromMedia() {
    setBusy(true);
    setError(null);
    try {
      if (source === "video") {
        if (!videoFile) throw new Error("Add a video first.");
        const job = await createArchiveJob("video", videoFile, { title });
        setSceneId(job.sceneId);
        const p = new URLSearchParams(params);
        p.set("scene", job.sceneId);
        p.set("step", "2");
        setParams(p);
        return;
      }
      if (source === "google_drive") {
        if (!online) throw new Error("Google Drive import needs an internet connection.");
        const job = await importGoogleDriveLink({ url: driveUrl, contentType: driveType, title });
        setSceneId(job.sceneId);
        setStep(2);
        return;
      }
      if (imageFiles.length === 1 && imageFiles[0].name.endsWith(".zip")) {
        const job = await uploadZip(imageFiles[0], title);
        setSceneId(job.sceneId);
        setStep(2);
        return;
      }
      if (imageFiles.length > 0) {
        const job = await uploadImages(imageFiles, { title });
        setSceneId(job.sceneId);
        setStep(2);
        return;
      }
      throw new Error("Add photos or a video first.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start");
    } finally {
      setBusy(false);
    }
  }

  async function handleRunQualityAndBuild() {
    if (!sceneId) return;
    setBusy(true);
    setError(null);
    try {
      const detail = await getScene(sceneId);
      const status = detail.metadata.status;
      if (status === "created") {
        await extractFrames(sceneId);
      } else if (status === "frames_ready") {
        await runColmap(sceneId);
      }
      setStep(4);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not continue");
    } finally {
      setBusy(false);
    }
  }

  async function handleBuildArchive() {
    if (!sceneId) return;
    setBusy(true);
    setError(null);
    try {
      await startArchiveBuild(sceneId);
      const detail = await getScene(sceneId);
      if (detail.metadata.status === "colmap_ready" || detail.metadata.status === "needs_rescan") {
        await trainSplat(sceneId);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not build archive");
    } finally {
      setBusy(false);
    }
  }

  function renderStepContent() {
    if (step === 1) {
      if (source === "video") {
        return (
          <VideoUploadPanel
            file={videoFile}
            title={title}
            onFileChange={setVideoFile}
            onTitleChange={setTitle}
          />
        );
      }
      if (source === "google_drive") {
        return (
          <GoogleDriveImportPanel
            url={driveUrl}
            contentType={driveType}
            title={title}
            onUrlChange={setDriveUrl}
            onContentTypeChange={setDriveType}
            onTitleChange={setTitle}
          />
        );
      }
      return (
        <BatchImageUploadPanel
          files={imageFiles}
          title={title}
          onFilesChange={setImageFiles}
          onTitleChange={setTitle}
        />
      );
    }
    if (step === 2) {
      return (
        <ReviewFilesStep
          source={source}
          fileNames={fileNames}
          title={title}
          totalSizeMb={totalSizeMb || undefined}
        />
      );
    }
    if (step === 3) {
      return <QualityCheckStep qa={qa} colmap={colmap} loading={qualityLoading} />;
    }
    if (step === 4 && sceneId) {
      return <BuildArchiveStep sceneId={sceneId} />;
    }
    if (step === 5 && sceneId) {
      return (
        <SceneAlignmentPanel
          sceneId={sceneId}
          metadata={metadata}
          onSaved={(next) => setMetadata(next)}
        />
      );
    }
    if (step === 6 && sceneId) {
      return <SceneViewerStep sceneId={sceneId} metadata={metadata} />;
    }
    if (step === 7 && sceneId) {
      return <ExportStep sceneId={sceneId} />;
    }
    return null;
  }

  const canNextStep1 =
    (source === "video" && !!videoFile) ||
    (source === "google_drive" && driveUrl.trim().length > 10 && online) ||
    (source !== "video" && source !== "google_drive" && imageFiles.length > 0);

  return (
    <div className="friendly-page wizard-page">
      <header className="friendly-hero">
        <div className="hero-copy">
          <h1>Create archive</h1>
          <p className="muted">Follow the steps to turn your media into a 3D archive.</p>
          <p className="hero-trust">Add media · Check quality · Create archive · Export/share</p>
        </div>
      </header>

      <WizardProgress currentStep={step} />

      <div className="wizard-content card">{renderStepContent()}</div>

      {error && <p className="error-text">{error}</p>}

      <div className="wizard-nav">
        {step > 1 && step !== 4 && (
          <button type="button" className="secondary" onClick={() => setStep(step - 1)}>
            Back
          </button>
        )}
        {step === 1 && (
          <button
            type="button"
            className="primary"
            disabled={!canNextStep1 || busy}
            onClick={handleStartFromMedia}
          >
            {busy ? "Starting…" : "Continue"}
          </button>
        )}
        {step === 2 && (
          <button type="button" className="primary" disabled={busy} onClick={() => setStep(3)}>
            Run quality check
          </button>
        )}
        {step === 3 && (
          <button
            type="button"
            className="primary"
            disabled={busy || !sceneId}
            onClick={handleRunQualityAndBuild}
          >
            {busy ? "Working…" : "Create archive"}
          </button>
        )}
        {step === 4 && sceneId && (
          <>
            <button type="button" className="secondary" disabled={busy} onClick={handleBuildArchive}>
              {busy ? "Building…" : "Start build"}
            </button>
            <button type="button" className="primary" onClick={() => setStep(5)}>
              Align scene
            </button>
          </>
        )}
        {step === 5 && (
          <button type="button" className="primary" onClick={() => setStep(6)}>
            View scene
          </button>
        )}
        {step === 6 && (
          <button type="button" className="primary" onClick={() => setStep(7)}>
            Export
          </button>
        )}
        {step === 7 && sceneId && (
          <Link to={`/scenes/${sceneId}`} className="primary">
            Open full workspace
          </Link>
        )}
      </div>

      <AdvancedSettingsPanel sceneId={sceneId ?? undefined} />
      <BackendStatusPanel />
    </div>
  );
}
