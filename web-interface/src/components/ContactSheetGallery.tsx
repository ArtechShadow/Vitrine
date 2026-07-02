import { useEffect, useMemo, useState } from "react";
import { contactSheetUrl } from "../api/client";
import ImageLightbox from "./ImageLightbox";

interface Props {
  sceneId: string;
  cacheBust?: string;
}

export default function ContactSheetGallery({ sceneId, cacheBust }: Props) {
  const [loadError, setLoadError] = useState(false);
  const [lightboxOpen, setLightboxOpen] = useState(false);

  const src = useMemo(() => {
    const bust = cacheBust ? `?t=${encodeURIComponent(cacheBust)}` : "";
    return contactSheetUrl(sceneId) + bust;
  }, [cacheBust, sceneId]);

  useEffect(() => {
    setLoadError(false);
    setLightboxOpen(false);
  }, [src]);

  if (loadError) {
    return (
      <div className="contact-sheet-gallery contact-sheet-gallery--empty">
        <p className="muted">Contact sheet is not ready yet.</p>
        <p className="muted">It will appear here automatically after media preparation finishes.</p>
      </div>
    );
  }

  return (
    <div className="contact-sheet-gallery">
      <div className="contact-sheet-header">
        <p className="muted">Full contact sheet - click to enlarge</p>
      </div>
      <button
        type="button"
        className="contact-sheet-image-button"
        onClick={() => setLightboxOpen(true)}
      >
        <img
          src={src}
          alt="Full contact sheet of extracted archive frames"
          className="contact-sheet-image"
          onError={() => setLoadError(true)}
        />
      </button>
      <ImageLightbox
        src={src}
        alt="Full contact sheet of extracted archive frames"
        open={lightboxOpen}
        onClose={() => setLightboxOpen(false)}
      />
    </div>
  );
}
