import { useCallback, useRef, useState } from "react";

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

interface VideoUploadPanelProps {
  file: File | null;
  title: string;
  onFileChange: (file: File | null) => void;
  onTitleChange: (title: string) => void;
}

export default function VideoUploadPanel({
  file,
  title,
  onFileChange,
  onTitleChange,
}: VideoUploadPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const acceptFile = useCallback(
    (candidate: File | undefined) => {
      if (!candidate) return;
      if (!isVideoFile(candidate)) {
        setError("Please choose a video file (MP4, MOV, MKV, WebM, AVI, or M4V).");
        return;
      }
      onFileChange(candidate);
      setError(null);
    },
    [onFileChange],
  );

  return (
    <div className="upload-panel">
      <h2>Add a walkthrough video</h2>
      <p className="muted">
        Use a slow, steady walk-through of the space. ArchiveSpace will copy the video into your
        local archive.
      </p>

      <div
        className={`friendly-dropzone ${file ? "has-file" : ""} ${dragging ? "is-dragging" : ""}`}
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragEnter={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          acceptFile(e.dataTransfer.files?.[0]);
        }}
      >
        <input
          ref={inputRef}
          type="file"
          className="upload-input-hidden"
          accept="video/*,.mp4,.mov,.mkv,.webm"
          onChange={(e) => acceptFile(e.target.files?.[0])}
        />
        {file ? (
          <>
            <p className="upload-file-name">{file.name}</p>
            <p className="muted">{(file.size / 1024 / 1024).toFixed(1)} MB — click to replace</p>
          </>
        ) : (
          <>
            <p className="friendly-dropzone-label">
              {dragging ? "Release to add video" : "Drop your video here"}
            </p>
            <p className="muted">or click to browse</p>
          </>
        )}
      </div>

      <div className="field">
        <label htmlFor="archive-title">Archive name (optional)</label>
        <input
          id="archive-title"
          value={title}
          onChange={(e) => onTitleChange(e.target.value)}
          placeholder="North Gallery, Spring 2026"
        />
      </div>

      {error && <p className="error-text">{error}</p>}
    </div>
  );
}