import { useState } from "react";
import { cancelJob, pauseJob, resumeJob } from "../api/client";
import ConfirmDialog from "./ConfirmDialog";

interface Props {
  sceneId: string;
  jobType: string;
  paused?: boolean;
  onChange?: () => void;
}

function IconPause() {
  return (
    <svg className="job-btn-icon" viewBox="0 0 16 16" aria-hidden>
      <rect x="3.5" y="2.5" width="3.5" height="11" rx="0.75" fill="currentColor" />
      <rect x="9" y="2.5" width="3.5" height="11" rx="0.75" fill="currentColor" />
    </svg>
  );
}

function IconPlay() {
  return (
    <svg className="job-btn-icon" viewBox="0 0 16 16" aria-hidden>
      <path d="M4.5 2.8v10.4c0 .7.8 1.1 1.4.7l7.8-5.2a.85.85 0 0 0 0-1.4L5.9 2.1c-.6-.4-1.4 0-1.4.7z" fill="currentColor" />
    </svg>
  );
}

function IconStop() {
  return (
    <svg className="job-btn-icon" viewBox="0 0 16 16" aria-hidden>
      <rect x="3.5" y="3.5" width="9" height="9" rx="1.25" fill="currentColor" />
    </svg>
  );
}

export default function JobControls({ sceneId, jobType, paused, onChange }: Props) {
  const [busy, setBusy] = useState(false);
  const [showCancel, setShowCancel] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      onChange?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="job-controls" role="group" aria-label="Processing controls">
        <div className={`job-controls-group${busy ? " is-busy" : ""}`}>
          {paused ? (
            <button
              type="button"
              className="job-btn job-btn-resume"
              disabled={busy}
              onClick={() => run(() => resumeJob(sceneId, jobType))}
            >
              <IconPlay />
              <span>Resume</span>
            </button>
          ) : (
            <button
              type="button"
              className="job-btn job-btn-pause"
              disabled={busy}
              onClick={() => run(() => pauseJob(sceneId, jobType))}
            >
              <IconPause />
              <span>Pause</span>
            </button>
          )}
          <span className="job-controls-divider" aria-hidden="true" />
          <button
            type="button"
            className="job-btn job-btn-cancel"
            disabled={busy}
            onClick={() => setShowCancel(true)}
          >
            <IconStop />
            <span>Cancel</span>
          </button>
        </div>
        {error && <p className="error-text job-controls-error">{error}</p>}
      </div>

      <ConfirmDialog
        open={showCancel}
        title="Cancel processing?"
        message="This stops the current job and prevents further automatic pipeline steps (COLMAP, previews, training). You can re-run steps manually later."
        confirmLabel="Cancel processing"
        danger
        busy={busy}
        onConfirm={() => {
          run(async () => {
            await cancelJob(sceneId, jobType, true);
            setShowCancel(false);
          });
        }}
        onCancel={() => !busy && setShowCancel(false)}
      />
    </>
  );
}