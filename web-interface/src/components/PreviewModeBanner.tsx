import { isPreviewMode } from "../lib/previewMode";

export default function PreviewModeBanner() {
  if (!isPreviewMode) return null;

  return (
    <div className="preview-mode-banner" role="status">
      <strong>UI preview</strong>
      <span>
        This is a hosted interface demo. Archives, uploads, and processing are simulated — the real
        pipeline runs locally with the ArchiveSpace worker.
      </span>
    </div>
  );
}