import { useOnline } from "../context/OnlineContext";

export default function OfflineModeIndicator() {
  const { online } = useOnline();

  return (
    <div
      className={`offline-indicator ${online ? "online" : "offline"}`}
      role="status"
      aria-live="polite"
    >
      <span className="offline-indicator-dot" aria-hidden />
      <span>{online ? "Online features available" : "Local mode - Drive import unavailable"}</span>
    </div>
  );
}
