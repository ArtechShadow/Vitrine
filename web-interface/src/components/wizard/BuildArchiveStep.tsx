import { useEffect, useState } from "react";
import { getArchiveJobStatus } from "../../api/archiveService";
import { isSceneBusy, type ProgressInfo } from "../../api/client";
import { useAppMode } from "../../context/AppModeContext";
import FriendlyStatusMessage from "../FriendlyStatusMessage";
import { friendlyJobType } from "../../lib/friendlyStatus";

interface BuildArchiveStepProps {
  sceneId: string;
}

export default function BuildArchiveStep({ sceneId }: BuildArchiveStepProps) {
  const { advancedMode } = useAppMode();
  const [status, setStatus] = useState("");
  const [progress, setProgress] = useState<ProgressInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function poll() {
      try {
        const detail = await getArchiveJobStatus(sceneId);
        if (!active) return;
        setStatus(detail.metadata.status);
        setProgress(
          detail.progress_train ??
            detail.progress_colmap ??
            detail.progress_extract ??
            detail.progress ??
            null,
        );
        setError(detail.metadata.last_error ?? null);
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : "Could not load status");
      }
    }

    poll();
    const id = setInterval(poll, 2000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [sceneId]);

  const busy = isSceneBusy(status) || status === "frames_ready" || status === "colmap_ready";
  const done = status === "ready";

  return (
    <div className="wizard-step-panel">
      <h2>Create archive</h2>
      <p className="muted">
        {done
          ? "Your 3D archive is ready to view."
          : busy
            ? "ArchiveSpace is building your 3D scene. This may take a while."
            : "Ready to build your archive."}
      </p>

      <FriendlyStatusMessage status={status} className="card" />

      {progress && (
        <div className="build-progress card">
          <div className="progress-bar">
            <div
              className="progress-bar-fill"
              style={{ width: `${Math.min(100, progress.percent ?? 0)}%` }}
            />
          </div>
          <p className="muted">{progress.message || friendlyJobType(progress.job_type)}</p>
          {advancedMode && progress.log_tail && (
            <pre className="log-tail">{progress.log_tail}</pre>
          )}
        </div>
      )}

      {error && <p className="error-text">{error}</p>}
    </div>
  );
}