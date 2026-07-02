import { useCallback, useEffect, useState } from "react";

interface Props {
  src: string;
  alt: string;
  open: boolean;
  onClose: () => void;
}

export default function ImageLightbox({ src, alt, open, onClose }: Props) {
  const [zoom, setZoom] = useState(1);

  const reset = useCallback(() => setZoom(1), []);

  useEffect(() => {
    if (!open) {
      reset();
      return;
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "+" || e.key === "=") setZoom((z) => Math.min(4, z + 0.25));
      if (e.key === "-") setZoom((z) => Math.max(0.5, z - 0.25));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, reset]);

  if (!open) return null;

  return (
    <div className="lightbox-backdrop" role="presentation" onClick={onClose}>
      <div className="lightbox-toolbar" onClick={(e) => e.stopPropagation()}>
        <button type="button" onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}>
          −
        </button>
        <span className="lightbox-zoom">{Math.round(zoom * 100)}%</span>
        <button type="button" onClick={() => setZoom((z) => Math.min(4, z + 0.25))}>
          +
        </button>
        <button type="button" onClick={reset}>
          Reset
        </button>
        <button type="button" onClick={onClose}>
          Close
        </button>
      </div>
      <div className="lightbox-stage" onClick={(e) => e.stopPropagation()}>
        <img
          src={src}
          alt={alt}
          className="lightbox-image"
          style={{ transform: `scale(${zoom})` }}
          draggable={false}
        />
      </div>
    </div>
  );
}