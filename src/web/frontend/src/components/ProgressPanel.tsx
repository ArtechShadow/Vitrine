// Live pipeline progress, driven by the SSE hook (poll fallback inside).
// Shows the Vitrine stage tracker, a percent bar, and a rolling log tail.

import { useEffect, useRef } from "react";
import { useProgress } from "../hooks/useProgress";
import { PIPELINE_STAGES, stageIndex, stageLabel } from "../lib/friendlyStatus";

interface Props {
  sceneId: string;
  /** Current scene status from the last detail fetch (seeds the tracker). */
  status: string;
  currentStage?: string;
  /** When false, no live connection is opened (scene already terminal). */
  active?: boolean;
  showLog?: boolean;
  onDone?: (status: string, error: string | null) => void;
}

export default function ProgressPanel({
  sceneId,
  status,
  currentStage,
  active = true,
  showLog = true,
  onDone,
}: Props) {
  const live = useProgress(sceneId, active);
  const logRef = useRef<HTMLPreElement>(null);
  const doneFiredRef = useRef(false);

  const effectiveStatus = live.status || status;
  const effectiveStage = live.stage || currentStage || "";
  const activeIndex = stageIndex(effectiveStatus, effectiveStage);

  useEffect(() => {
    if (live.done && !doneFiredRef.current) {
      doneFiredRef.current = true;
      onDone?.(live.status, live.error);
    }
  }, [live.done, live.status, live.error, onDone]);

  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [live.logs]);

  const percent = Math.round(live.percent);

  return (
    <div className="progress-panel">
      <div className="progress-head">
        <span className="progress-stage">
          {live.done
            ? live.error
              ? "Stopped"
              : "Complete"
            : effectiveStage
              ? stageLabel(effectiveStage)
              : "Preparing…"}
        </span>
        <span className="progress-percent">{percent}%</span>
      </div>

      <div className="progress-bar" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
        <div
          className={`progress-bar-fill ${live.error ? "is-error" : ""}`}
          style={{ width: `${Math.max(2, percent)}%` }}
        />
      </div>

      <ol className="stage-tracker" aria-label="Pipeline stages">
        {PIPELINE_STAGES.map((stage, i) => {
          const stateClass =
            activeIndex < 0 ? "" : i < activeIndex ? "done" : i === activeIndex ? "active" : "pending";
          return (
            <li key={stage} className={`stage-dot ${stateClass}`} title={stageLabel(stage)}>
              <span className="stage-dot-mark" aria-hidden />
              <span className="stage-dot-label">{stageLabel(stage)}</span>
            </li>
          );
        })}
      </ol>

      {live.error && <p className="error-text">{live.error}</p>}

      {showLog && live.logs.length > 0 && (
        <details className="progress-log" open>
          <summary>
            Activity log
            <span className="transport-tag">{live.transport === "poll" ? "polling" : "live"}</span>
          </summary>
          <pre ref={logRef} className="log-tail">
            {live.logs.join("\n")}
          </pre>
        </details>
      )}
    </div>
  );
}
