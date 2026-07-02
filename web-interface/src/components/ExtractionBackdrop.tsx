interface Props {
  src: string | null;
  frameCount?: number;
  expected?: number;
  fps?: number;
  paused?: boolean;
}

export default function ExtractionBackdrop({
  src,
  frameCount,
  expected,
  fps,
  paused,
}: Props) {
  return (
    <div className="extraction-backdrop" aria-hidden>
      {src ? (
        <img src={src} alt="" className="extraction-backdrop-img" />
      ) : (
        <div className="extraction-backdrop-fallback" />
      )}
      <div className="extraction-backdrop-scrim" />
      <div className="extraction-backdrop-badge">
        <span className="extraction-backdrop-live">{paused ? "Paused" : "Live extraction"}</span>
        {frameCount != null && (
          <span className="extraction-backdrop-count">
            {frameCount.toLocaleString()}
            {expected != null ? ` / ~${expected.toLocaleString()}` : ""} frames
          </span>
        )}
        {fps != null && <span className="extraction-backdrop-fps">{fps} FPS</span>}
      </div>
    </div>
  );
}