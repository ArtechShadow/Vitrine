import { resolvePipelineSteps, type PipelineRuntimeFlags } from "../lib/pipelineSteps";
import type { SceneMetadata } from "../api/client";

interface Props {
  meta: SceneMetadata;
  flags?: PipelineRuntimeFlags;
  detail?: string;
  compact?: boolean;
  embedded?: boolean;
  /** Single-row layout for scene cards — sits beside the status badge */
  inline?: boolean;
}

export default function PipelineTrack({
  meta,
  flags,
  detail,
  compact,
  embedded,
  inline,
}: Props) {
  const steps = resolvePipelineSteps(meta, flags);

  return (
    <nav
      className={[
        "pipeline-track",
        compact ? "pipeline-track--compact" : "",
        embedded ? "pipeline-track--embedded" : "",
        inline ? "pipeline-track--inline" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      aria-label="Processing pipeline"
    >
      <ol className="pipeline-track-list">
        {steps.map((step, index) => (
          <li key={step.id} className="pipeline-track-item">
            <div
              className={`pipeline-track-step pipeline-track-step--${step.state}`}
              aria-current={step.state === "active" ? "step" : undefined}
              title={step.label}
            >
              <span className="pipeline-track-marker" aria-hidden>
                {index + 1}
              </span>
              <span className="pipeline-track-label">{step.short}</span>
            </div>
            {index < steps.length - 1 && (
              <span className="pipeline-track-connector" aria-hidden />
            )}
          </li>
        ))}
      </ol>
      {detail ? <p className="pipeline-track-detail muted">{detail}</p> : null}
    </nav>
  );
}