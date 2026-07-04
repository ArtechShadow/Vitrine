// Scene workspace: tabbed viewer + metadata sidebar. Rewrite of PR #6's
// SceneWorkspace/SceneDetail, trimmed to the endpoints we actually serve.

import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  deleteScene,
  exportUrl,
  getScene,
  sceneSplatUrl,
  type SceneDetail,
} from "../api/client";
import { isSceneBusy, isSceneReady } from "../lib/friendlyStatus";
import { formatBytes, formatTimestamp, inputTypeLabel } from "../lib/format";
import SplatViewer from "../components/SplatViewer";
import FrameGallery from "../components/FrameGallery";
import QaSwipeReview from "../components/QaSwipeReview";
import ProgressPanel from "../components/ProgressPanel";
import StatusBadge from "../components/StatusBadge";
import ConfirmDialog from "../components/ConfirmDialog";

type Tab = "scene" | "frames" | "quality" | "activity";

export default function SceneWorkspace() {
  const { sceneId } = useParams<{ sceneId: string }>();
  const navigate = useNavigate();

  const [detail, setDetail] = useState<SceneDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("scene");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(
    (silent = false) => {
      if (!sceneId) return;
      if (!silent) setLoading(true);
      getScene(sceneId)
        .then((d) => {
          setDetail(d);
          setError(null);
        })
        .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load archive"))
        .finally(() => {
          if (!silent) setLoading(false);
        });
    },
    [sceneId],
  );

  useEffect(() => {
    load();
  }, [load]);

  const status = detail?.metadata.status ?? "";
  const busy = isSceneBusy(status);
  const ready = isSceneReady(status);

  useEffect(() => {
    if (!busy) return;
    const id = window.setInterval(() => load(true), 5000);
    return () => window.clearInterval(id);
  }, [busy, load]);

  const splatSource = useMemo(() => (detail ? sceneSplatUrl(detail.metadata) : null), [detail]);

  const doDelete = useCallback(async () => {
    if (!sceneId) return;
    setDeleting(true);
    try {
      await deleteScene(sceneId);
      navigate("/library");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove archive");
      setDeleting(false);
      setConfirmDelete(false);
    }
  }, [sceneId, navigate]);

  if (!sceneId) return null;
  if (loading && !detail) return <div className="page"><p className="muted">Loading archive…</p></div>;
  if (error && !detail) return <div className="page"><p className="error-text">{error}</p></div>;
  if (!detail) return null;

  const meta = detail.metadata;
  const meshPath = meta.outputs?.mesh;

  const TABS: readonly [Tab, string][] = [
    ["scene", "3D scene"],
    ["frames", "Frames"],
    ["quality", "Quality"],
    ["activity", "Activity"],
  ];

  return (
    <div className="page workspace-page">
      <header className="workspace-header">
        <div>
          <button type="button" className="link-btn" onClick={() => navigate("/library")}>
            ← My archives
          </button>
          <h1>{meta.title}</h1>
          <StatusBadge status={meta.status} currentStage={meta.current_stage} />
        </div>
        <div className="workspace-header-actions">
          {ready && (
            <a className="secondary" href={exportUrl(sceneId)} download>
              Download .zip
            </a>
          )}
          <button type="button" className="danger" onClick={() => setConfirmDelete(true)}>
            Remove
          </button>
        </div>
      </header>

      <div className="workspace-body">
        <div className="workspace-main">
          <nav className="tabs" role="tablist">
            {TABS.map(([id, label]) => (
              <button
                key={id}
                role="tab"
                type="button"
                aria-selected={tab === id}
                className={`tab ${tab === id ? "active" : ""}`}
                onClick={() => setTab(id)}
              >
                {label}
              </button>
            ))}
          </nav>

          <div className="tab-panel card">
            {tab === "scene" &&
              (splatSource ? (
                <SplatViewer sceneId={sceneId} title={meta.title} sceneTransform={meta.sceneTransform} splatFile={splatSource.split("/").pop()} />
              ) : (
                <div className="empty-state">
                  <p className="muted">
                    {busy ? "The 3D splat is still being built — check the Activity tab." : "No splat is available for this archive."}
                  </p>
                </div>
              ))}
            {tab === "frames" && <FrameGallery sceneId={sceneId} />}
            {tab === "quality" && <QaSwipeReview sceneId={sceneId} qa={detail.qa_report} />}
            {tab === "activity" && (
              <ProgressPanel
                sceneId={sceneId}
                status={status}
                currentStage={meta.current_stage}
                active={busy}
                onDone={() => load(true)}
              />
            )}
          </div>
        </div>

        <aside className="workspace-sidebar card">
          <h2>Details</h2>
          <dl className="meta-list">
            <dt>Source</dt>
            <dd>{inputTypeLabel(meta.source_type)}</dd>
            {meta.filename && (
              <>
                <dt>File</dt>
                <dd className="wrap">{meta.filename}</dd>
              </>
            )}
            {meta.image_count ? (
              <>
                <dt>Photos</dt>
                <dd>{meta.image_count}</dd>
              </>
            ) : null}
            {meta.file_size_bytes ? (
              <>
                <dt>Size</dt>
                <dd>{formatBytes(meta.file_size_bytes)}</dd>
              </>
            ) : null}
            {meta.created_at != null && (
              <>
                <dt>Created</dt>
                <dd>{formatTimestamp(meta.created_at)}</dd>
              </>
            )}
            {meta.finished_at != null && (
              <>
                <dt>Finished</dt>
                <dd>{formatTimestamp(meta.finished_at)}</dd>
              </>
            )}
          </dl>

          {meshPath && (
            <a className="link-btn" href={`/api/scenes/${encodeURIComponent(sceneId)}/derivatives/${meshPath}`} download>
              Download scene mesh
            </a>
          )}

          {meta.error && <p className="error-text">{meta.error}</p>}
        </aside>
      </div>

      <ConfirmDialog
        open={confirmDelete}
        title="Remove archive?"
        message={`Remove "${meta.title}" and its outputs from this machine? This cannot be undone.`}
        confirmLabel="Remove permanently"
        danger
        busy={deleting}
        onConfirm={doDelete}
        onCancel={() => !deleting && setConfirmDelete(false)}
      />
    </div>
  );
}
