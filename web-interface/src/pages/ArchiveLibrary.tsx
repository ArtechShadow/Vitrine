import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { deleteScene, isSceneBusy, type SceneMetadata } from "../api/client";
import { getSceneList } from "../api/archiveService";
import ArchiveCard from "../components/archive/ArchiveCard";
import ConfirmDialog from "../components/ConfirmDialog";
type FilterKey = "all" | "working" | "ready" | "issue";

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
    getSceneList()
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
      if (filter === "working" && !isSceneBusy(scene.status)) return false;
      if (filter === "ready" && scene.status !== "ready") return false;
      if (filter === "issue" && !scene.status.includes("failed") && scene.status !== "needs_rescan")
        return false;
      if (!q) return true;
      const hay = [scene.title, scene.scene_id, scene.location, scene.creator]
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
      setError(e instanceof Error ? e.message : "Could not remove archive");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="friendly-page archive-library-page">
      <header className="friendly-hero">
        <h1>My archives</h1>
        <p className="muted">Your saved 3D archives on this computer.</p>
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
          {(
            [
              ["all", "All"],
              ["working", "In progress"],
              ["ready", "Ready"],
              ["issue", "Needs attention"],
            ] as const
          ).map(([key, label]) => (
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

      <div className="archive-grid">
        {filtered.map((scene) => (
          <ArchiveCard
            key={scene.scene_id}
            scene={scene}
            busy={isSceneBusy(scene.status)}
            onDelete={() => setDeleteTarget(scene)}
          />
        ))}
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        title="Remove archive?"
        message={
          deleteTarget
            ? `Remove "${deleteTarget.title || deleteTarget.scene_id}" from this computer? This cannot be undone.`
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