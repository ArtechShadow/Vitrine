// Read-only frame gallery with a lightbox. Harvested from PR #6's FrameGallery
// (the cull controls are intentionally dropped in v1 — files_api is read-only).

import { useCallback, useEffect, useState } from "react";
import { frameUrl, listFrames } from "../api/frames";

interface Props {
  sceneId: string;
  limit?: number;
}

export default function FrameGallery({ sceneId, limit = 60 }: Props) {
  const [frames, setFrames] = useState<string[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState<string | null>(null);

  const load = useCallback(
    (nextOffset: number) => {
      setLoading(true);
      listFrames(sceneId, limit, nextOffset)
        .then((res) => {
          setFrames(res.frames);
          setTotal(res.total);
          setOffset(res.offset);
          setError(null);
        })
        .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load frames"))
        .finally(() => setLoading(false));
    },
    [sceneId, limit],
  );

  useEffect(() => {
    load(0);
  }, [load]);

  if (loading && frames.length === 0) return <p className="muted">Loading frames…</p>;
  if (error) return <p className="error-text">{error}</p>;
  if (frames.length === 0) return <p className="muted">No frames extracted yet.</p>;

  const hasPrev = offset > 0;
  const hasNext = offset + frames.length < total;

  return (
    <div className="frame-gallery">
      <div className="frame-gallery-head">
        <span className="muted">
          {total > 0 ? `${offset + 1}–${offset + frames.length} of ${total} frames` : `${frames.length} frames`}
        </span>
        {(hasPrev || hasNext) && (
          <div className="frame-pager">
            <button type="button" disabled={!hasPrev || loading} onClick={() => load(Math.max(0, offset - limit))}>
              Previous
            </button>
            <button type="button" disabled={!hasNext || loading} onClick={() => load(offset + limit)}>
              Next
            </button>
          </div>
        )}
      </div>

      <div className="frame-grid">
        {frames.map((name) => (
          <button
            key={name}
            type="button"
            className="frame-thumb"
            onClick={() => setLightbox(frameUrl(sceneId, name))}
            title={name}
          >
            <img src={frameUrl(sceneId, name)} alt={name} loading="lazy" />
          </button>
        ))}
      </div>

      {lightbox && (
        <div className="dialog-backdrop" role="presentation" onClick={() => setLightbox(null)}>
          <img className="lightbox-image" src={lightbox} alt="Frame preview" onClick={(e) => e.stopPropagation()} />
        </div>
      )}
    </div>
  );
}
