import { formatEnergyCost, formatEta, type ProgressInfo } from "../api/client";
import JobControls from "./JobControls";

const DEFAULT_STAGES = [
  "Step 1",
  "Step 2",
  "Step 3",
  "Step 4",
];

interface Props {
  title: string;
  progress: ProgressInfo | null;
  running: boolean;
  paused?: boolean;
  stages?: string[];
  sceneId?: string;
  jobType?: string;
  onJobControl?: () => void;
}

export default function ProcessingPanel({
  title,
  progress,
  running,
  paused,
  stages = DEFAULT_STAGES,
  sceneId,
  jobType,
  onJobControl,
}: Props) {
  if (!running && !paused && !progress) return null;

  const percent = progress?.percent ?? 0;
  const stageLabel = progress?.stage_label ?? progress?.stage ?? "Starting…";
  const stageIndex = Math.max(0, (progress?.stage_index ?? 1) - 1);
  const showControls = !!(sceneId && jobType && (running || paused));

  return (
    <div className="processing-panel card">
      <div className="processing-header">
        <h2>{title}</h2>
        <div className="processing-header-actions">
          {paused && <span className="badge">Paused</span>}
          {running && !paused && <span className="badge running">Live</span>}
          {showControls && (
            <JobControls
              sceneId={sceneId}
              jobType={jobType}
              paused={paused}
              onChange={onJobControl}
            />
          )}
        </div>
      </div>

      <div className="progress-bar-track">
        <div className="progress-bar-fill" style={{ width: `${Math.min(100, percent)}%` }} />
      </div>

      <div className="progress-stats">
        <span>{percent.toFixed(0)}%</span>
        <span className="muted">{progress?.message ?? "Working…"}</span>
        {running && progress?.eta_seconds != null && (
          <span className="eta">{formatEta(progress.eta_seconds)} remaining</span>
        )}
      </div>

      <div className="stage-stepper">
        {stages.map((label, i) => (
          <div
            key={label}
            className={`stage-step ${i < stageIndex ? "done" : ""} ${i === stageIndex && (running || paused) ? "active" : ""}`}
          >
            <span className="stage-dot" />
            <span className="stage-name">{label}</span>
          </div>
        ))}
      </div>

      <p className="muted current-stage">Current: {stageLabel}</p>

      {progress?.metrics && (
        <div className="live-metrics">
          {progress.metrics.frame_count != null && (
            <span>
              {progress.metrics.frame_count.toLocaleString()}
              {progress.metrics.expected_frames != null
                ? ` / ~${progress.metrics.expected_frames.toLocaleString()}`
                : ""}{" "}
              frames
            </span>
          )}
          {progress.metrics.fps != null && (
            <span className="muted">{progress.metrics.fps} FPS</span>
          )}
          {progress.metrics.registered_images != null && (
            <span>{progress.metrics.registered_images} images registered</span>
          )}
          {progress.metrics.point_count != null && (
            <span>{progress.metrics.point_count.toLocaleString()} sparse points</span>
          )}
        </div>
      )}

      {progress?.energy && progress.energy.cost_pence > 0 && (
        <p className="muted energy-running-total">
          Running energy total: {formatEnergyCost(progress.energy.cost_pence)} ({progress.energy.energy_wh.toFixed(2)} Wh)
        </p>
      )}

      {progress?.log_tail && (
        <details className="log-details" open={running && progress?.stage !== "qa"}>
          <summary>Live log</summary>
          <pre className="log-tail">{progress.log_tail}</pre>
        </details>
      )}
    </div>
  );
}