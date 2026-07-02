interface Props {
  message?: string;
  hint?: string;
}

export default function PreviewPlaceholder({
  message = "3D preview not ready yet",
  hint,
}: Props) {
  return (
    <div className="preview-placeholder" role="status" aria-live="polite">
      <img src="/logo.jpg" alt="" className="preview-placeholder-logo" />
      <p className="preview-placeholder-message">{message}</p>
      {hint && <p className="preview-placeholder-hint muted">{hint}</p>}
    </div>
  );
}