// Pipeline overview: backend capabilities + active runs. Optional panels are
// gated on /api/tools — when that endpoint is unavailable the page degrades to
// "capabilities unknown" and still shows live runs. No calls are made to
// endpoints Vitrine does not implement.

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listScenes, type SceneMetadata } from "../api/client";
import { isSceneBusy } from "../lib/friendlyStatus";
import { useTools, hasFeature } from "../hooks/useTools";
import StatusBadge from "../components/StatusBadge";

const CAPABILITIES: readonly [string, string][] = [
  ["ffmpeg", "Frame extraction"],
  ["colmap", "Camera reconstruction (SfM)"],
  ["splat_training", "3D splat training"],
  ["mesh", "Scene mesh extraction"],
  ["objects", "Object reconstruction"],
  ["drive_ingest", "Google Drive ingest"],
];

export default function Pipeline() {
  const { tools, loading, unavailable } = useTools();
  const [scenes, setScenes] = useState<SceneMetadata[]>([]);

  useEffect(() => {
    listScenes()
      .then(setScenes)
      .catch(() => setScenes([]));
  }, []);

  const active = scenes.filter((s) => isSceneBusy(s.status));

  return (
    <div className="page pipeline-page">
      <header className="hero compact">
        <h1>Pipeline</h1>
        <p className="muted">What this machine can do, and what it is doing right now.</p>
      </header>

      <section className="card">
        <div className="section-heading">
          <h2>Capabilities</h2>
          {unavailable && <p className="muted">Capability reporting is unavailable — showing all as unknown.</p>}
        </div>
        {loading ? (
          <p className="muted">Checking tools…</p>
        ) : (
          <ul className="capability-list">
            {CAPABILITIES.map(([key, label]) => {
              const available = hasFeature(tools, key);
              const state = unavailable ? "unknown" : available ? "available" : "unavailable";
              return (
                <li key={key} className={`capability capability-${state}`}>
                  <span className="capability-dot" aria-hidden />
                  <span className="capability-label">{label}</span>
                  <span className="capability-state muted">{state}</span>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="card">
        <div className="section-heading">
          <h2>Active runs</h2>
          <Link to="/library" className="link-btn">
            All archives
          </Link>
        </div>
        {active.length === 0 ? (
          <p className="muted">Nothing is processing right now.</p>
        ) : (
          <ul className="active-runs">
            {active.map((s) => (
              <li key={s.scene_id}>
                <Link to={`/scenes/${s.scene_id}`} className="active-run-title">
                  {s.title}
                </Link>
                <StatusBadge status={s.status} currentStage={s.current_stage} compact />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
