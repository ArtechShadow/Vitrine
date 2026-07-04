// Library grid card (rewrite of PR #6's ArchiveCard).

import { Link } from "react-router-dom";
import { thumbnailUrl, type SceneMetadata } from "../api/client";
import { inputTypeLabel, formatBytes, formatTimestamp } from "../lib/format";
import { isSceneReady } from "../lib/friendlyStatus";
import StatusBadge from "./StatusBadge";

interface Props {
  scene: SceneMetadata;
  onDelete: () => void;
}

export default function SceneCard({ scene, onDelete }: Props) {
  const thumb = thumbnailUrl(scene);
  const ready = isSceneReady(scene.status);

  return (
    <article className="scene-card card">
      <Link to={`/scenes/${scene.scene_id}`} className="scene-card-media" aria-label={`Open ${scene.title}`}>
        {thumb ? (
          <img src={thumb} alt={scene.title} loading="lazy" />
        ) : (
          <span className="scene-card-placeholder">{inputTypeLabel(scene.source_type)}</span>
        )}
      </Link>

      <div className="scene-card-body">
        <div className="scene-card-heading">
          <Link to={`/scenes/${scene.scene_id}`} className="scene-card-title">
            {scene.title}
          </Link>
          <StatusBadge status={scene.status} currentStage={scene.current_stage} compact />
        </div>

        <p className="scene-card-meta muted">
          {inputTypeLabel(scene.source_type)}
          {scene.image_count ? ` · ${scene.image_count} photos` : ""}
          {scene.file_size_bytes ? ` · ${formatBytes(scene.file_size_bytes)}` : ""}
        </p>
        {scene.created_at != null && (
          <p className="scene-card-meta muted">{formatTimestamp(scene.created_at)}</p>
        )}

        <div className="scene-card-actions">
          <Link to={`/scenes/${scene.scene_id}`} className="link-btn">
            Open
          </Link>
          {ready && (
            <a className="link-btn" href={`/api/scenes/${encodeURIComponent(scene.scene_id)}/export`} download>
              Download
            </a>
          )}
          <button type="button" className="link-btn danger-text" onClick={onDelete}>
            Remove
          </button>
        </div>
      </div>
    </article>
  );
}
