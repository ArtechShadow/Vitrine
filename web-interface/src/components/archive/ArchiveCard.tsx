import { Link } from "react-router-dom";
import type { SceneMetadata } from "../../api/client";
import { sceneThumbnailUrl } from "../../api/client";
import { useAppMode } from "../../context/AppModeContext";
import FriendlyStatusMessage from "../FriendlyStatusMessage";
import { inputTypeLabel } from "../../lib/qualitySummary";

interface ArchiveCardProps {
  scene: SceneMetadata;
  onDelete?: () => void;
  busy?: boolean;
}

export default function ArchiveCard({ scene, onDelete, busy }: ArchiveCardProps) {
  const { advancedMode } = useAppMode();
  const thumb = sceneThumbnailUrl(scene);
  const inputType = inputTypeLabel(scene.source_type);
  const qualityLabel = scene.status === "ready" ? "Quality checked" : scene.status === "needs_rescan" ? "Needs another capture" : "Quality pending";
  const qualityClass = scene.status === "ready" ? "success" : scene.status === "needs_rescan" ? "warning" : "";

  return (
    <article className="archive-card card">
      <div className="archive-card-thumb">
        {thumb ? (
          <img src={thumb} alt="" loading="lazy" />
        ) : (
          <div className="archive-card-thumb-placeholder">No preview</div>
        )}
      </div>
      <div className="archive-card-body">
        <h3>{scene.title || "Untitled archive"}</h3>
        <p className="muted archive-card-meta">
          {new Date(scene.created_at).toLocaleDateString()} · {inputType}
        </p>
        <FriendlyStatusMessage status={scene.status} />
        <span className={`archive-quality badge ${qualityClass}`}>{qualityLabel}</span>
        {advancedMode && (
          <div className="archive-card-advanced">
            <p className="muted mono small">Job ID: {scene.scene_id}</p>
            <p className="muted mono small">Raw status: {scene.status}</p>
            {scene.splat?.path && <p className="muted mono small">Scene path: {scene.splat.path}</p>}
            {scene.processing_pipeline && (
              <p className="muted mono small">
                Metadata: {Object.keys(scene.processing_pipeline).length} process records
              </p>
            )}
          </div>
        )}
      </div>
      <div className="archive-card-actions">
        <Link to={`/scenes/${scene.scene_id}`} className="primary small-btn">
          View
        </Link>
        <Link to={`/create?scene=${scene.scene_id}&step=export`} className="secondary small-btn">
          Export
        </Link>
        {advancedMode && (
          <Link to={`/scenes/${scene.scene_id}`} className="secondary small-btn">
            Details
          </Link>
        )}
        {onDelete && (
          <button
            type="button"
            className="danger-text small-btn"
            disabled={busy}
            onClick={onDelete}
          >
            Remove
          </button>
        )}
      </div>
    </article>
  );
}
