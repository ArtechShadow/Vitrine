// Friendly status pill (rewrite of PR #6's FriendlyStatusMessage) driven by
// OUR job vocabulary.

import { friendlyStatus, statusTone } from "../lib/friendlyStatus";

interface Props {
  status: string;
  currentStage?: string;
  compact?: boolean;
}

export default function StatusBadge({ status, currentStage, compact = false }: Props) {
  const tone = statusTone(status);
  const busy = tone === "working";
  return (
    <span className={`status-badge tone-${tone} ${compact ? "compact" : ""}`}>
      {busy && <span className="status-spinner" aria-hidden />}
      {friendlyStatus(status, currentStage)}
    </span>
  );
}
