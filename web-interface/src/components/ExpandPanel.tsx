import { useEffect, type ReactNode } from "react";

interface Props {
  open: boolean;
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
  size?: "lg" | "full";
}

export default function ExpandPanel({
  open,
  title,
  subtitle,
  onClose,
  children,
  size = "lg",
}: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="expand-backdrop" role="presentation" onClick={onClose}>
      <div
        className={`expand-panel expand-panel--${size}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="expand-panel-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="expand-panel-header">
          <div className="expand-panel-heading">
            <h2 id="expand-panel-title">{title}</h2>
            {subtitle ? <p className="muted expand-panel-subtitle">{subtitle}</p> : null}
          </div>
          <button type="button" className="expand-panel-close" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>
        <div className="expand-panel-body">{children}</div>
      </div>
    </div>
  );
}