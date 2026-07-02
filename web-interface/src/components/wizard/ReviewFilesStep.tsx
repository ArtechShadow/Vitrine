import type { InputSource } from "../../api/archiveService";

interface ReviewFilesStepProps {
  source: InputSource;
  fileNames: string[];
  title: string;
  totalSizeMb?: number;
}

export default function ReviewFilesStep({
  source,
  fileNames,
  title,
  totalSizeMb,
}: ReviewFilesStepProps) {
  const sourceLabel =
    source === "video"
      ? "Walkthrough video"
      : source === "google_drive"
        ? "Google Drive import"
        : source === "zip"
          ? "ZIP archive"
          : "Photo set";

  return (
    <div className="wizard-step-panel">
      <h2>Review your files</h2>
      <p className="muted">Check everything looks right before we run a quality check.</p>

      <dl className="review-summary card">
        <dt>Archive name</dt>
        <dd>{title || "Untitled archive"}</dd>
        <dt>Input type</dt>
        <dd>{sourceLabel}</dd>
        <dt>Files</dt>
        <dd>{fileNames.length}</dd>
        {totalSizeMb != null && (
          <>
            <dt>Total size</dt>
            <dd>{totalSizeMb.toFixed(1)} MB</dd>
          </>
        )}
      </dl>

      <ul className="file-review-items card">
        {fileNames.map((name) => (
          <li key={name}>{name}</li>
        ))}
      </ul>
    </div>
  );
}