import { useState } from "react";
import { exportArchive, exportForUnreal } from "../../api/archiveService";
import { useAppMode } from "../../context/AppModeContext";

interface ExportStepProps {
  sceneId: string;
}

export default function ExportStep({ sceneId }: ExportStepProps) {
  const { advancedMode } = useAppMode();
  const [exporting, setExporting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleExportArchive() {
    setExporting(true);
    setError(null);
    try {
      const result = await exportArchive(sceneId);
      setMessage("Archive package ready. Download will be available when export is fully connected.");
      if (advancedMode) setMessage(`Export URL: ${result.downloadUrl}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  async function handleUnrealExport() {
    setExporting(true);
    setError(null);
    try {
      const result = await exportForUnreal(sceneId);
      setMessage(`Game engine export ${result.status}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="wizard-step-panel">
      <h2>Export &amp; share</h2>
      <p className="muted">Save your archive for viewing elsewhere or for use in another app.</p>

      <div className="export-actions">
        <button type="button" className="primary" disabled={exporting} onClick={handleExportArchive}>
          Save archive package
        </button>
        <button type="button" className="secondary" disabled title="Immersive viewer is currently disabled">
          Immersive viewer disabled
        </button>
        {advancedMode && (
          <button type="button" className="secondary" disabled={exporting} onClick={handleUnrealExport}>
            Game engine export
          </button>
        )}
      </div>

      {message && <p className="success-text">{message}</p>}
      {error && <p className="error-text">{error}</p>}

      <p className="muted field-hint">
        Files stay on this computer. Nothing is uploaded to the cloud unless you choose an online
        import.
      </p>
    </div>
  );
}
