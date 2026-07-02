import { useEffect, useState } from "react";
import { frameUrl, listFrames } from "../api/client";
import ImageLightbox from "./ImageLightbox";

interface Props {
  sceneId: string;
  cacheBust?: string;
}

export default function FrameGallery({ sceneId, cacheBust }: Props) {
  const [frames, setFrames] = useState<string[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [lightbox, setLightbox] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    listFrames(sceneId, 60)
      .then((data) => {
        setFrames(data.frames);
        setTotal(data.total);
      })
      .catch(() => {
        setFrames([]);
        setTotal(0);
      })
      .finally(() => setLoading(false));
  }, [sceneId, cacheBust]);

  if (loading) return <p className="muted">Loading frames…</p>;
  if (!frames.length) return <p className="muted">No frames extracted yet.</p>;

  const bust = cacheBust ? `?t=${cacheBust}` : "";

  return (
    <div className="frame-gallery">
      <div className="frame-gallery-header">
        <p className="muted">
          {total.toLocaleString()} frames · click to enlarge
        </p>
      </div>
      <div className="frame-strip">
        {frames.map((name) => (
          <button
            key={name}
            type="button"
            className="frame-thumb"
            onClick={() => setLightbox(name)}
            title={name}
          >
            <img src={frameUrl(sceneId, name) + bust} alt={name} loading="lazy" />
          </button>
        ))}
      </div>
      {total > frames.length && (
        <p className="muted frame-more">Showing first {frames.length} of {total}</p>
      )}
      <ImageLightbox
        src={lightbox ? frameUrl(sceneId, lightbox) + bust : ""}
        alt={lightbox ?? "Frame"}
        open={!!lightbox}
        onClose={() => setLightbox(null)}
      />
    </div>
  );
}