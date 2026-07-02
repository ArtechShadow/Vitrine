// Read-only QA review (v1). Harvested from PR #6's QaSwipeReview but stripped
// of the cull action — it presents each reviewed frame with its verdict
// (sharp / blurry / duplicate) and lets the curator page through. Wiring a
// destructive cull endpoint is deferred until files_api gains a write path.

import { useEffect, useMemo, useState } from "react";
import { frameUrl } from "../api/frames";
import type { QaFrame, QaReport } from "../api/client";

interface Props {
  sceneId: string;
  qa: QaReport | null;
}

function verdict(frame: QaFrame): { label: string; tone: string } {
  if (frame.duplicate) return { label: "Duplicate", tone: "warn" };
  if (frame.blurry) return { label: "Blurry", tone: "failed" };
  return { label: "Sharp", tone: "ready" };
}

export default function QaSwipeReview({ sceneId, qa }: Props) {
  const frames = useMemo<QaFrame[]>(() => qa?.frames ?? [], [qa]);
  const [index, setIndex] = useState(0);

  useEffect(() => {
    setIndex(0);
  }, [sceneId, frames.length]);

  useEffect(() => {
    if (frames.length === 0) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") setIndex((i) => Math.min(frames.length - 1, i + 1));
      if (e.key === "ArrowLeft") setIndex((i) => Math.max(0, i - 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [frames.length]);

  if (frames.length === 0) {
    return <p className="muted">No per-frame quality results are available for this capture yet.</p>;
  }

  const frame = frames[Math.min(index, frames.length - 1)];
  const v = verdict(frame);

  return (
    <div className="qa-review">
      <div className="qa-review-stage">
        <img className="qa-review-image" src={frameUrl(sceneId, frame.name)} alt={frame.name} />
        <span className={`status-badge tone-${v.tone}`}>{v.label}</span>
      </div>
      <div className="qa-review-meta">
        <span className="muted">{frame.name}</span>
        {typeof frame.blur_score === "number" && (
          <span className="muted">Sharpness score {frame.blur_score.toFixed(0)}</span>
        )}
      </div>
      <div className="qa-review-nav">
        <button type="button" disabled={index === 0} onClick={() => setIndex((i) => Math.max(0, i - 1))}>
          Previous
        </button>
        <span className="muted">
          {index + 1} / {frames.length}
        </span>
        <button
          type="button"
          disabled={index >= frames.length - 1}
          onClick={() => setIndex((i) => Math.min(frames.length - 1, i + 1))}
        >
          Next
        </button>
      </div>
    </div>
  );
}
