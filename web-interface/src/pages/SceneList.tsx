import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  deleteScene,
  formatStatus,
  isSceneBusy,
  listScenes,
  sceneThumbnailUrl,
  type SceneMetadata,
} from "../api/client";
import PipelineTrack from "../components/PipelineTrack";
import ConfirmDialog from "../components/ConfirmDialog";
import GaussianSplatBackground from "../components/GaussianSplatBackground";

type FilterKey = "all" | "processing" | "ready" | "failed";

function statusBadge(status: string) {
  if (status === "frames_ready" || status === "colmap_ready" || status === "ready") return "success";
  if (status?.includes("failed")) return "error";
  if (isSceneBusy(status)) return "running";
  return "";
}

function pipelineFlags(scene: SceneMetadata) {
  return {
    extractRunning: scene.status === "extracting_frames" || scene.status === "created",
    colmapRunning:
      scene.status === "colmap_running" || scene.status === "colmap_recovery_running",
    trainRunning: scene.status === "training",
  };
}

interface SceneListProps {
  activeSceneId?: string;
}

export default function SceneList({ activeSceneId }: SceneListProps = {}) {
  const [scenes, setScenes] = useState<SceneMetadata[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<FilterKey>("all");
  const [deleteTarget, setDeleteTarget] = useState<SceneMetadata | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback((silent = false) => {
    if (!silent) setLoading(true);
    listScenes()
      .then(setScenes)
      .catch((e) => setError(e.message))
      .finally(() => {
        if (!silent) setLoading(false);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const hasBusy = useMemo(() => scenes.some((s) => isSceneBusy(s.status)), [scenes]);

  useEffect(() => {
    if (!hasBusy) return;
    const id = setInterval(() => load(true), 2500);
    return () => clearInterval(id);
  }, [hasBusy, load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return scenes.filter((scene) => {
      if (filter === "processing" && !isSceneBusy(scene.status)) return false;
      if (filter === "ready" && scene.status !== "ready" && scene.status !== "colmap_ready") return false;
      if (filter === "failed" && !scene.status.includes("failed")) return false;
      if (!q) return true;
      const hay = [
        scene.title,
        scene.scene_id,
        scene.location,
        scene.creator,
        scene.status,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [scenes, query, filter]);

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteScene(deleteTarget.scene_id);
      setScenes((prev) => prev.filter((s) => s.scene_id !== deleteTarget.scene_id));
      setDeleteTarget(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="scene-library">
      <GaussianSplatBackground />
      <div className="scene-library-content">
      <div className="library-header">
        <div className="library-header-title">
          <h1>Scene library</h1>
          <p className="muted">Preserved captures · processing status</p>
        </div>
        <div className="list-toolbar card">
          <input
            type="search"
            placeholder="Search title, location, ID…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search scenes"
          />
          <div className="filter-chips" role="group" aria-label="Filter scenes">
            {(["all", "processing", "ready", "failed"] as FilterKey[]).map((key) => (
              <button
                key={key}
                type="button"
                className={`chip ${filter === key ? "active" : ""}`}
                onClick={() => setFilter(key)}
              >
                {key === "all" ? "All" : key.charAt(0).toUpperCase() + key.slice(1)}
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading && <p className="muted">Loading scenes…</p>}
      {error && <p className="error-text">{error}</p>}

      {!loading && filtered.length === 0 && (
        <div className="card empty-state">
          <p>{scenes.length === 0 ? "No scenes yet." : "No scenes match your filters."}</p>
          {scenes.length === 0 && (
            <p className="muted">
              <Link to="/upload">Upload a gallery video</Link> to create your first scene package.
            </p>
          )}
        </div>
      )}

      <div className="scene-grid-wrap">
      <div className="scene-grid">
        {filtered.map((scene) => {
          const thumb = sceneThumbnailUrl(scene);
          const busy = isSceneBusy(scene.status);
          const isActive = activeSceneId === scene.scene_id;
          return (
            <article key={scene.scene_id} className={`scene-card scene-card--compact ${isActive ? "is-active" : ""}`}>
              <Link to={`/scenes/${scene.scene_id}`} className="scene-card-link">
                <div className="scene-thumb">
                  {thumb ? (
                    <img src={thumb} alt="" loading="lazy" />
                  ) : (
                    <div className="scene-thumb-placeholder">
                      <span>{scene.extraction?.frame_count ? "…" : "—"}</span>
                    </div>
                  )}
                </div>
                <div className="scene-card-body">
                  <div className="scene-card-top">
                    <h3>{scene.title || scene.scene_id}</h3>
                  </div>
                  <p className="muted scene-card-meta">
                    {[
                      scene.scene_id,
                      scene.extraction?.frame_count ? `${scene.extraction.frame_count} fr` : null,
                      scene.colmap?.registered_images
                        ? `COLMAP ${scene.colmap.registered_images}`
                        : null,
                      scene.location,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                  <div className="scene-card-status-row">
                    <PipelineTrack
                      meta={scene}
                      flags={pipelineFlags(scene)}
                      compact
                      embedded
                      inline
                    />
                    <span className={`badge ${statusBadge(scene.status)}`}>
                      {formatStatus(scene.status)}
                    </span>
                  </div>
                </div>
              </Link>
              <div className="scene-card-actions">
                <button
                  type="button"
                  className="danger-text"
                  disabled={busy}
                  title={busy ? "Wait until processing finishes" : "Delete scene"}
                  onClick={() => setDeleteTarget(scene)}
                >
                  Delete
                </button>
              </div>
            </article>
          );
        })}
      </div>
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete scene?"
        message={
          deleteTarget
            ? `Permanently remove "${deleteTarget.title || deleteTarget.scene_id}" and all frames, COLMAP data, and splats. This cannot be undone.`
            : ""
        }
        confirmLabel="Delete permanently"
        danger
        busy={deleting}
        onConfirm={confirmDelete}
        onCancel={() => !deleting && setDeleteTarget(null)}
      />
      </div>
    </div>
  );
}