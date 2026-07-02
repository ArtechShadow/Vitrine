import { useCallback, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { uploadVideo } from "../api/client";
import { DEFAULT_QA_PRESET, getQaPreset, QA_PRESETS, type QaPresetId } from "../lib/qaPresets";

const VIDEO_TYPES = new Set([
  "video/mp4",
  "video/quicktime",
  "video/x-matroska",
  "video/webm",
  "video/x-msvideo",
  "video/x-m4v",
]);

const VIDEO_EXT = /\.(mp4|mov|mkv|webm|avi|m4v)$/i;

function isVideoFile(file: File): boolean {
  return VIDEO_TYPES.has(file.type) || VIDEO_EXT.test(file.name);
}

interface UploadProps {
  embedded?: boolean;
  onComplete?: (sceneId: string) => void;
}

export default function Upload({ embedded, onComplete }: UploadProps = {}) {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [qaPreset, setQaPreset] = useState<QaPresetId>(DEFAULT_QA_PRESET.id);
  const [fps, setFps] = useState(DEFAULT_QA_PRESET.fps);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const acceptFile = useCallback((candidate: File | undefined) => {
    if (!candidate) return;
    if (!isVideoFile(candidate)) {
      setError("Please add a video file: MP4, MOV, MKV, WebM, AVI, or M4V.");
      return;
    }
    setFile(candidate);
    setError(null);
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setError("Choose or drop a video file");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const preset = getQaPreset(qaPreset);
      const result = await uploadVideo(file, {
        title,
        fps,
        autoExtract: true,
        qaPreset,
        blurThreshold: preset.blurThreshold,
        duplicateThreshold: preset.duplicateThreshold,
      });
      if (onComplete) onComplete(result.scene_id);
      else navigate(`/scenes/${result.scene_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  function handlePresetChange(nextPreset: QaPresetId) {
    const preset = getQaPreset(nextPreset);
    setQaPreset(nextPreset);
    setFps(preset.fps);
  }

  function onDragOver(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setDragging(true);
  }

  function onDragLeave(e: React.DragEvent) {
    e.preventDefault();
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setDragging(false);
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setDragging(false);
    acceptFile(e.dataTransfer.files?.[0]);
  }

  return (
    <div className={`upload-page ${embedded ? "upload-page--embedded" : ""}`}>
      <div className={`page-title ${embedded ? "page-title--embedded upload-page-title" : "page-title--compact"}`}>
        <h1>New capture</h1>
        <p className="muted">Add a walk-through video. ArchiveSpace will build the scene package automatically.</p>
      </div>

      <form className={`upload-form card ${embedded ? "upload-form--embedded" : ""}`} onSubmit={handleSubmit}>
        <div className="upload-grid">
          <div className="upload-dropzone-col">
            <div
              className={`upload-dropzone ${file ? "has-file" : ""} ${dragging ? "is-dragging" : ""}`}
              role="button"
              tabIndex={0}
              onClick={() => inputRef.current?.click()}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  inputRef.current?.click();
                }
              }}
              onDragEnter={onDragOver}
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              onDrop={onDrop}
            >
              <input
                ref={inputRef}
                id="file"
                type="file"
                className="upload-input-hidden"
                accept="video/mp4,video/quicktime,video/x-matroska,video/webm,.mp4,.mov,.mkv,.webm"
                onChange={(e) => acceptFile(e.target.files?.[0])}
              />
              <span className="upload-dropzone-icon" aria-hidden>
                {dragging ? "v" : "+"}
              </span>
              {file ? (
                <>
                  <p className="upload-file-name">{file.name}</p>
                  <p className="muted upload-dropzone-hint">
                    Ready to start - {(file.size / 1024 / 1024).toFixed(1)} MB - click or drop to replace
                  </p>
                </>
              ) : (
                <>
                  <p className="upload-dropzone-label">
                    {dragging ? "Release to add video" : "Drop a video here"}
                  </p>
                  <p className="muted upload-dropzone-hint">or click to choose MP4, MOV, MKV, or WebM</p>
                </>
              )}
            </div>
          </div>

          <div className="upload-fields-col">
            <div className="upload-step-list" aria-label="Capture workflow">
              <div>
                <span>1</span>
                <strong>Add video</strong>
                <small>Use a slow, steady walk-through.</small>
              </div>
              <div>
                <span>2</span>
                <strong>Check frames</strong>
                <small>Blurry and duplicate frames are flagged.</small>
              </div>
              <div>
                <span>3</span>
                <strong>Build 3D scan</strong>
                <small>The camera match starts automatically.</small>
              </div>
            </div>

            <div className="upload-fields-grid">
              <div className="field">
                <label htmlFor="title">Scene name</label>
                <input
                  id="title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="North Gallery, Spring 2026"
                />
              </div>
              <div className="field">
                <label htmlFor="fps">Frame detail</label>
                <input
                  id="fps"
                  type="number"
                  min={0.5}
                  max={30}
                  step={0.5}
                  value={fps}
                  onChange={(e) => setFps(parseFloat(e.target.value))}
                />
              </div>
              <div className="field field--full upload-preset-field">
                <label htmlFor="qa-preset">Capture type</label>
                <select
                  id="qa-preset"
                  value={qaPreset}
                  onChange={(e) => handlePresetChange(e.target.value as QaPresetId)}
                >
                  {QA_PRESETS.map((preset) => (
                    <option key={preset.id} value={preset.id}>
                      {preset.label}
                    </option>
                  ))}
                </select>
                <p className="muted field-hint">{getQaPreset(qaPreset).description}</p>
              </div>
            </div>

            <p className="muted field-hint upload-fps-hint">
              Higher frame detail can help difficult scans, but it takes longer.
            </p>
            {error && <p className="error-text">{error}</p>}
            <button type="submit" className="primary upload-submit" disabled={uploading || !file}>
              {uploading ? "Starting capture..." : "Start capture"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
