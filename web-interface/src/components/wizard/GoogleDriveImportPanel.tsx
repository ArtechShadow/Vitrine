import { useOnline } from "../../context/OnlineContext";
import type { GoogleDriveContentType } from "../../api/archiveService";

interface GoogleDriveImportPanelProps {
  url: string;
  contentType: GoogleDriveContentType;
  title: string;
  onUrlChange: (url: string) => void;
  onContentTypeChange: (type: GoogleDriveContentType) => void;
  onTitleChange: (title: string) => void;
}

const CONTENT_OPTIONS: { value: GoogleDriveContentType; label: string }[] = [
  { value: "video", label: "A video" },
  { value: "photos", label: "A folder of photos" },
  { value: "zip", label: "A ZIP file" },
  { value: "project", label: "An existing ArchiveSpace project" },
  { value: "unknown", label: "Not sure" },
];

export default function GoogleDriveImportPanel({
  url,
  contentType,
  title,
  onUrlChange,
  onContentTypeChange,
  onTitleChange,
}: GoogleDriveImportPanelProps) {
  const { online } = useOnline();

  if (!online) {
    return (
      <div className="upload-panel">
        <h2>Import from Google Drive</h2>
        <div className="card offline-feature-notice">
          <p>
            <strong>Online feature</strong>
          </p>
          <p className="muted">
            Google Drive import needs an internet connection. You can still open saved local
            archives.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="upload-panel">
      <h2>Import from Google Drive</h2>
      <p className="muted">
        Paste a shared Google Drive link. ArchiveSpace will copy the files into your local archive.
        Your original Drive files will not be changed.
      </p>

      <div className="field">
        <label htmlFor="drive-url">Paste Google Drive link</label>
        <input
          id="drive-url"
          type="url"
          value={url}
          onChange={(e) => onUrlChange(e.target.value)}
          placeholder="https://drive.google.com/..."
        />
      </div>

      <fieldset className="field">
        <legend>What does this link contain?</legend>
        <div className="radio-group">
          {CONTENT_OPTIONS.map((opt) => (
            <label key={opt.value} className="radio-label">
              <input
                type="radio"
                name="drive-content"
                value={opt.value}
                checked={contentType === opt.value}
                onChange={() => onContentTypeChange(opt.value)}
              />
              {opt.label}
            </label>
          ))}
        </div>
      </fieldset>

      <div className="field">
        <label htmlFor="drive-title">Archive name (optional)</label>
        <input
          id="drive-title"
          value={title}
          onChange={(e) => onTitleChange(e.target.value)}
          placeholder="Imported from Drive"
        />
      </div>
    </div>
  );
}
