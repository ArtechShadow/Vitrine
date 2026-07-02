// Source-picker landing page. Harvested from PR #6's HomePage: each capture
// source is a card that deep-links into the wizard at /create?source=X.

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listScenes, type SceneMetadata } from "../api/client";
import { inputTypeLabel } from "../lib/format";
import StatusBadge from "../components/StatusBadge";

interface SourceOption {
  id: string;
  label: string;
  title: string;
  description: string;
  action: string;
  path: string;
}

const SOURCES: readonly SourceOption[] = [
  {
    id: "video",
    label: "Video",
    title: "Add a video",
    description: "Use a walkthrough video of a room, object, or gallery.",
    action: "Choose video",
    path: "/create?source=video",
  },
  {
    id: "photos",
    label: "Photos",
    title: "Add photos",
    description: "Upload multiple images or a folder of photographs. Stills beat video for sharpness.",
    action: "Choose photos",
    path: "/create?source=photos",
  },
  {
    id: "zip",
    label: "Folder or ZIP",
    title: "Add a folder or ZIP",
    description: "Bring in a prepared image set or archive package.",
    action: "Choose folder / ZIP",
    path: "/create?source=zip",
  },
  {
    id: "drive",
    label: "Google Drive",
    title: "Import from Google Drive",
    description: "Paste a shared Drive link to copy a capture into Vitrine.",
    action: "Paste Drive link",
    path: "/create?source=google_drive",
  },
] as const;

const JOURNEY: readonly [string, string][] = [
  ["Add media", "Choose video, photos, a folder/ZIP, or a Drive link."],
  ["Review", "Vitrine checks what you added."],
  ["Quality check", "Blur, coverage, and duplicates are assessed."],
  ["Build", "The 3D splat and scene are reconstructed locally."],
  ["View", "Open the browsable 3D scene."],
  ["Export", "Download the run archive."],
];

export default function HomePage() {
  const navigate = useNavigate();
  const [recent, setRecent] = useState<SceneMetadata[]>([]);

  useEffect(() => {
    listScenes()
      .then((items) => setRecent(items.slice(0, 3)))
      .catch(() => setRecent([]));
  }, []);

  return (
    <div className="page home-page">
      <header className="hero">
        <div className="hero-copy">
          <h1>What would you like to archive?</h1>
          <p className="muted">
            Build a browsable 3D archive from video, photos, folders, ZIP files, or Google Drive. Everything is
            processed locally on this machine.
          </p>
          <p className="hero-trust">Runs locally · reached over an SSH tunnel · no cloud upload</p>
        </div>
        <div className="hero-actions">
          <button type="button" className="primary" onClick={() => navigate("/create")}>
            Create new archive
          </button>
          <button type="button" className="secondary" onClick={() => navigate("/library")}>
            Open my archives
          </button>
        </div>
      </header>

      <div className="source-cards">
        {SOURCES.map((opt) => (
          <button key={opt.id} type="button" className="source-card card" onClick={() => navigate(opt.path)}>
            <span className="source-card-label">{opt.label}</span>
            <span className="source-card-title">{opt.title}</span>
            <span className="source-card-desc muted">{opt.description}</span>
            <span className="source-card-action">{opt.action}</span>
          </button>
        ))}
      </div>

      <div className="home-columns">
        <section className="card">
          <div className="section-heading">
            <h2>Your archive journey</h2>
            <p className="muted">A guided path from raw media to a saved 3D archive.</p>
          </div>
          <ol className="journey-steps">
            {JOURNEY.map(([title, text], i) => (
              <li key={title}>
                <span className="journey-step-num">{i + 1}</span>
                <strong>{title}</strong>
                <span className="muted">{text}</span>
              </li>
            ))}
          </ol>
        </section>

        <section className="card">
          <div className="section-heading compact">
            <h2>Recent archives</h2>
            <button type="button" className="link-btn" onClick={() => navigate("/library")}>
              View all
            </button>
          </div>
          {recent.length > 0 ? (
            <ul className="recent-list">
              {recent.map((scene) => (
                <li key={scene.scene_id}>
                  <button type="button" className="recent-open" onClick={() => navigate(`/scenes/${scene.scene_id}`)}>
                    <strong>{scene.title}</strong>
                    <small className="muted">{inputTypeLabel(scene.source_type)}</small>
                  </button>
                  <StatusBadge status={scene.status} currentStage={scene.current_stage} compact />
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No saved archives yet. Create one when you are ready.</p>
          )}
        </section>
      </div>
    </div>
  );
}
