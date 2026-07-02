import { useEffect, useRef, useState } from "react";
import { frameUrl } from "../api/frames";

const CYCLE_MS = 920;

interface Props {
  sceneId: string;
  liveFrame?: string;
  liveBlurScore?: number;
  liveDuplicate?: boolean;
  liveDecision?: "keep" | "remove";
  cacheBust?: string;
  analyzed?: number;
  total?: number;
}

type Decision = "keep" | "remove";

function autoDecision(blurScore: number, duplicate: boolean): Decision {
  return blurScore < 50 || duplicate ? "remove" : "keep";
}

export default function QaSwipeReview({
  sceneId,
  liveFrame,
  liveBlurScore = 0,
  liveDuplicate = false,
  liveDecision,
  cacheBust,
  analyzed,
  total,
}: Props) {
  const [cardFrame, setCardFrame] = useState<string | null>(null);
  const [cardBlur, setCardBlur] = useState(0);
  const [cardDuplicate, setCardDuplicate] = useState(false);
  const [decision, setDecision] = useState<Decision>("keep");
  const [cycleKey, setCycleKey] = useState(0);
  const [bgPulse, setBgPulse] = useState(false);
  const lastFrameRef = useRef<string | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current != null) window.clearTimeout(timerRef.current);
    };
  }, []);

  useEffect(() => {
    if (!liveFrame || liveFrame === lastFrameRef.current) return;
    lastFrameRef.current = liveFrame;

    const nextDecision = liveDecision ?? autoDecision(liveBlurScore, liveDuplicate);
    setCardFrame(liveFrame);
    setCardBlur(liveBlurScore);
    setCardDuplicate(liveDuplicate);
    setDecision(nextDecision);
    setCycleKey((k) => k + 1);
    setBgPulse(true);

    if (timerRef.current != null) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => setBgPulse(false), CYCLE_MS);
  }, [liveFrame, liveBlurScore, liveDuplicate, liveDecision]);

  const bust = cacheBust ? `?t=${encodeURIComponent(cacheBust)}` : "";

  return (
    <div className="qa-swipe-backdrop is-auto" aria-hidden>
      <div
        key={`remove-${cycleKey}`}
        className={`qa-swipe-bg qa-swipe-bg--remove ${bgPulse && decision === "remove" ? "is-pulsing" : ""}`}
      >
        <span className="qa-swipe-label">Remove</span>
      </div>
      <div
        key={`keep-${cycleKey}`}
        className={`qa-swipe-bg qa-swipe-bg--keep ${bgPulse && decision === "keep" ? "is-pulsing" : ""}`}
      >
        <span className="qa-swipe-label">Keep</span>
      </div>

      <div className="qa-swipe-scrim" />

      {cardFrame && (
        <div className="qa-swipe-auto-card-wrap">
          <div
            key={`${cardFrame}-${cycleKey}`}
            className={`qa-swipe-card qa-swipe-card--auto qa-swipe-card--cycle-${decision}`}
          >
            <img src={frameUrl(sceneId, cardFrame) + bust} alt="" draggable={false} />
            <span className={`qa-swipe-stamp qa-swipe-stamp--${decision}`}>
              {decision === "remove" ? "REMOVE" : "KEEP"}
            </span>
          </div>
        </div>
      )}

      <div className="qa-swipe-auto-badge">
        <span className="qa-swipe-live">QA analysis</span>
        {analyzed != null && total != null && (
          <span className="qa-swipe-backdrop-count">
            {analyzed} / {total} frames
          </span>
        )}
        {cardFrame && (
          <span className="qa-swipe-backdrop-meta">
            blur {cardBlur.toFixed(1)}
            {cardDuplicate ? " · duplicate" : ""}
          </span>
        )}
      </div>
    </div>
  );
}