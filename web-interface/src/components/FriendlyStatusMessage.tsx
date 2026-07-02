import { useAppMode } from "../context/AppModeContext";
import { friendlyStatus } from "../lib/friendlyStatus";

interface FriendlyStatusMessageProps {
  status: string;
  message?: string;
  className?: string;
}

export default function FriendlyStatusMessage({
  status,
  message,
  className = "",
}: FriendlyStatusMessageProps) {
  const { advancedMode } = useAppMode();
  const friendly = friendlyStatus(status);

  return (
    <div className={`friendly-status ${className}`}>
      <span className="friendly-status-label">{message ?? friendly}</span>
      {advancedMode && status !== friendly && (
        <span className="friendly-status-raw muted">{status}</span>
      )}
    </div>
  );
}