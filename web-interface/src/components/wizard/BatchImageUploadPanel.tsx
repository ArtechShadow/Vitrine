import { useCallback, useRef, useState } from "react";

const IMAGE_EXT = /\.(jpe?g|png|webp|heic|tif?f)$/i;
const ZIP_EXT = /\.zip$/i;

function isImageFile(file: File): boolean {
  return file.type.startsWith("image/") || IMAGE_EXT.test(file.name);
}

function isZipFile(file: File): boolean {
  return file.type === "application/zip" || ZIP_EXT.test(file.name);
}

interface BatchImageUploadPanelProps {
  files: File[];
  title: string;
  onFilesChange: (files: File[]) => void;
  onTitleChange: (title: string) => void;
}

export default function BatchImageUploadPanel({
  files,
  title,
  onFilesChange,
  onTitleChange,
}: BatchImageUploadPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);
  const zipRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const addFiles = useCallback(
    (incoming: FileList | File[] | null) => {
      if (!incoming?.length) return;
      const list = Array.from(incoming).filter((file) => isImageFile(file) || isZipFile(file));
      if (!list.length) {
        setError("No supported files found. Use images or a ZIP file.");
        return;
      }
      if (list.some(isZipFile)) {
        onFilesChange([list.find(isZipFile)!]);
        setError(null);
        return;
      }
      onFilesChange([...files, ...list]);
      setError(null);
    },
    [files, onFilesChange],
  );

  return (
    <div className="upload-panel">
      <h2>Add photos</h2>
      <p className="muted">
        Upload a set of images, pick a folder of photos, or add a ZIP file. Files are copied into
        your local archive.
      </p>

      <div
        className={`friendly-dropzone ${isDragging ? "is-dragging" : ""} ${files.length ? "has-file" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setIsDragging(false);
          addFiles(event.dataTransfer.files);
        }}
      >
        <strong>Drag photos or a ZIP file here</strong>
        <p className="muted">Or choose files from this computer.</p>
        <div className="upload-actions-row">
          <button type="button" className="secondary" onClick={() => inputRef.current?.click()}>
            Choose images
          </button>
          <button type="button" className="secondary" onClick={() => folderRef.current?.click()}>
            Choose folder
          </button>
          <button type="button" className="secondary" onClick={() => zipRef.current?.click()}>
            Choose ZIP
          </button>
        </div>
      </div>

      <input
        ref={inputRef}
        type="file"
        className="upload-input-hidden"
        accept="image/*,.jpg,.jpeg,.png,.webp"
        multiple
        onChange={(e) => addFiles(e.target.files)}
      />
      <input
        ref={folderRef}
        type="file"
        className="upload-input-hidden"
        // @ts-expect-error webkitdirectory is non-standard but widely supported
        webkitdirectory=""
        multiple
        onChange={(e) => addFiles(e.target.files)}
      />
      <input
        ref={zipRef}
        type="file"
        className="upload-input-hidden"
        accept=".zip,application/zip"
        onChange={(e) => {
          const zip = e.target.files?.[0];
          if (zip) onFilesChange([zip]);
        }}
      />

      {files.length > 0 && (
        <div className="file-review-list card">
          <p>
            <strong>{files.length}</strong> file{files.length !== 1 ? "s" : ""} selected
          </p>
          <div className="quality-preview">
            <span className="quality-rating quality-rating--okay">Estimated quality: Review needed</span>
            <p className="muted">Some photos may be blurry, but you can still try creating an archive.</p>
            <ul>
              <li>Duplicate warning: similar photos will be checked before building.</li>
              <li>Blur warning: soft images may reduce scene quality.</li>
              <li>Missing angles advice: add more views around the subject when possible.</li>
            </ul>
          </div>
          <ul className="file-review-items">
            {files.slice(0, 8).map((f) => (
              <li key={`${f.name}-${f.size}`}>{f.name}</li>
            ))}
            {files.length > 8 && <li className="muted">…and {files.length - 8} more</li>}
          </ul>
          <button type="button" className="link-btn" onClick={() => onFilesChange([])}>
            Clear selection
          </button>
          <p className="muted field-hint">Continue anyway is available after review if the capture is imperfect.</p>
        </div>
      )}

      <div className="field">
        <label htmlFor="photo-archive-title">Archive name (optional)</label>
        <input
          id="photo-archive-title"
          value={title}
          onChange={(e) => onTitleChange(e.target.value)}
          placeholder="Exhibition photos, March 2026"
        />
      </div>

      {error && <p className="error-text">{error}</p>}
      {files.length > 0 && files[0].name.endsWith(".zip") && (
        <p className="muted field-hint">
          ZIP import will be processed when the backend endpoint is connected.
        </p>
      )}
    </div>
  );
}
