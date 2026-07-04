// Library grid with search + status filter chips + confirm-delete. Rewrite of
// PR #6's ArchiveLibrary against OUR scene list. Busy scenes trigger a light
// background refresh (SSE drives the per-scene detail views; the grid only
// needs coarse polling to reflect completion).

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { deleteScene, listScenes, type SceneMetadata } from "../api/client";
import { isSceneBusy, isSceneFailed, isSceneReady } from "../lib/friendlyStatus";
import SceneCard from "../components/SceneCard";
import ConfirmDialog from "../components/ConfirmDialog";

type FilterKey = "all" | "working" | "ready" | "issue";

const FILTERS: readonly [FilterKey, string][] = [
  ["all", "All"],
  ["working", "In progress"],
  ["ready", "Ready"],
  ["issue", "Needs attention"],
];

export default function ArchiveLibrary() {
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
      .then((items) => {
        setScenes(items);
        setError(null);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load archives"))
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
    const id = window.setInterval(() => load(true), 4000);
    return () => window.clearInterval(id);
  }, [hasBusy, load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return scenes.filter((scene) => {
      if (filter === "working" && !isSceneBusy(scene.status)) return false;
      if (filter === "ready" && !isSceneReady(scene.status)) return false;
      if (filter === "issue" && !isSceneFailed(scene.status)) return false;
      if (!q) return true;
      return [scene.title, scene.scene_id, scene.filename].filter(Boolean).join(" ").toLowerCase().includes(q);
    });
  }, [scenes, query, filter]);

  const confirmDelete = useCallback(async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteScene(deleteTarget.scene_id);
      setScenes((prev) => prev.filter((s) => s.scene_id !== deleteTarget.scene_id));
      setDeleteTarget(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove archive");
    } finally {
      setDeleting(false);
    }
  }, [deleteTarget]);

  return (
    <div className="page library-page">
      <header className="hero compact">
        <h1>My archives</h1>
        <p className="muted">Your saved 3D archives on this machine.</p>
      </header>

      <div className="library-toolbar card">
        <input
          type="search"
          placeholder="Search archives…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search archives"
        />
        <div className="filter-chips" role="group" aria-label="Filter archives">
          {FILTERS.map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={`chip ${filter === key ? "active" : ""}`}
              onClick={() => setFilter(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {loading && <p className="muted">Loading archives…</p>}
      {error && <p className="error-text">{error}</p>}

      {!loading && filtered.length === 0 && (
        <div className="card empty-state">
          <p>{scenes.length === 0 ? "No archives yet." : "No archives match your search."}</p>
          <Link to="/create?source=video" className="primary">
            Create your first archive
          </Link>
        </div>
      )}

      <div className="scene-grid">
        {filtered.map((scene) => (
          <SceneCard key={scene.scene_id} scene={scene} onDelete={() => setDeleteTarget(scene)} />
        ))}
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        title="Remove archive?"
        message={
          deleteTarget
            ? `Remove "${deleteTarget.title}" from this machine? This deletes its outputs and cannot be undone.`
            : ""
        }
        confirmLabel="Remove permanently"
        danger
        busy={deleting}
        onConfirm={confirmDelete}
        onCancel={() => !deleting && setDeleteTarget(null)}
      />
    </div>
  );
}
