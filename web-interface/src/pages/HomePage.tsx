import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { SceneMetadata } from "../api/client";
import { getSceneList } from "../api/archiveService";
import FriendlyStatusMessage from "../components/FriendlyStatusMessage";
import { useOnline } from "../context/OnlineContext";
import { inputTypeLabel } from "../lib/qualitySummary";

const OPTIONS = [
  {
    id: "video",
    label: "Video",
    title: "Add a video",
    description: "Use a walkthrough video of a room, object, or gallery.",
    action: "Choose video",
    path: "/create?source=video",
    icon: "video",
  },
  {
    id: "photos",
    label: "Photos",
    title: "Add photos",
    description: "Upload multiple images or a folder of photographs.",
    action: "Choose photos",
    path: "/create?source=photos",
    icon: "photos",
  },
  {
    id: "zip",
    label: "Folder or ZIP",
    title: "Add a folder or ZIP",
    description: "Bring in a prepared image set or archive package.",
    action: "Choose folder / ZIP",
    path: "/create?source=zip",
    icon: "folder",
  },
  {
    id: "drive",
    label: "Google Drive",
    title: "Import from Google Drive",
    description: "Paste a shared Drive link to copy files into ArchiveSpace.",
    action: "Paste Drive link",
    path: "/create?source=google_drive",
    online: true,
    icon: "drive",
  },
  {
    id: "existing",
    label: "Existing archive",
    title: "Open existing archive",
    description: "Continue from a saved ArchiveSpace project.",
    action: "Open library",
    path: "/library",
    icon: "archive",
  },
] as const;

const JOURNEY = [
  ["Add media", "Choose video, photos, folder, ZIP, or Drive."],
  ["Review files", "ArchiveSpace checks what you added."],
  ["Check quality", "We look for blur, missing angles, and duplicate images."],
  ["Create archive", "The 3D archive is built locally."],
  ["View scene", "Open the browsable 3D scene."],
  ["Export or share", "Save the archive package or export for another tool."],
] as const;

const TIPS = [
  "Move slowly",
  "Capture from different angles",
  "Avoid heavy blur",
  "Keep the subject well lit",
  "Take more photos than you think you need",
];

function HomeIcon({ type }: { type: (typeof OPTIONS)[number]["icon"] }) {
  const common = {
    viewBox: "0 0 24 24",
    "aria-hidden": true,
    focusable: false,
  };

  if (type === "video") {
    return (
      <svg {...common}>
        <path d="M4 7.5A2.5 2.5 0 0 1 6.5 5h7A2.5 2.5 0 0 1 16 7.5v9a2.5 2.5 0 0 1-2.5 2.5h-7A2.5 2.5 0 0 1 4 16.5v-9Z" />
        <path d="m16 10 4-2.5v9L16 14v-4Z" />
      </svg>
    );
  }
  if (type === "photos") {
    return (
      <svg {...common}>
        <path d="M5 6.5A2.5 2.5 0 0 1 7.5 4h9A2.5 2.5 0 0 1 19 6.5v11a2.5 2.5 0 0 1-2.5 2.5h-9A2.5 2.5 0 0 1 5 17.5v-11Z" />
        <path d="m7 16 3.2-3.4 2.3 2.4 1.5-1.5L17 17" />
        <path d="M9 8.5h.01" />
      </svg>
    );
  }
  if (type === "folder") {
    return (
      <svg {...common}>
        <path d="M3.8 7.5A2.5 2.5 0 0 1 6.3 5h4l2 2h5.4a2.5 2.5 0 0 1 2.5 2.5v7A2.5 2.5 0 0 1 17.7 19H6.3a2.5 2.5 0 0 1-2.5-2.5v-9Z" />
        <path d="M8 12h8" />
        <path d="M8 15h5" />
      </svg>
    );
  }
  if (type === "drive") {
    return (
      <svg {...common}>
        <path d="m9 4-6 10 3 5h12l3-5-6-10H9Z" />
        <path d="m9 4 3 5 3-5" />
        <path d="m3 14 6 .1" />
        <path d="m21 14-6 .1" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M5 5.5A2.5 2.5 0 0 1 7.5 3h9A2.5 2.5 0 0 1 19 5.5v13A2.5 2.5 0 0 1 16.5 21h-9A2.5 2.5 0 0 1 5 18.5v-13Z" />
      <path d="M8 8h8" />
      <path d="M8 12h8" />
      <path d="M8 16h5" />
    </svg>
  );
}

export default function HomePage() {
  const navigate = useNavigate();
  const { online } = useOnline();
  const [recent, setRecent] = useState<SceneMetadata[]>([]);

  useEffect(() => {
    getSceneList()
      .then((items) => setRecent(items.slice(0, 3)))
      .catch(() => setRecent([]));
  }, []);

  const localStatus = useMemo(
    () => (online ? "Drive import is available. Local archives still stay on this computer." : "You can create and open local archives. Google Drive import waits until internet is available."),
    [online],
  );

  return (
    <div className="friendly-page home-page">
      <header className="friendly-hero">
        <div className="hero-copy">
          <h1>What would you like to archive?</h1>
          <p className="muted">
            Create a browsable 3D archive from video, photos, folders, ZIP files, or Google Drive.
            Everything is copied safely into your local archive.
          </p>
          <p className="hero-trust">Works locally · USB friendly · No technical setup needed</p>
        </div>
        <div className="hero-actions" aria-label="Quick actions">
          <button type="button" className="primary" onClick={() => navigate("/create")}>
            Create new archive
          </button>
          <button type="button" className="secondary" onClick={() => navigate("/library")}>
            Open existing archive
          </button>
        </div>
      </header>

      <div className="home-cards">
        {OPTIONS.map((opt) => (
          <button
            key={opt.id}
            type="button"
            className="home-card card"
            onClick={() => navigate(opt.path)}
          >
            <span className="home-card-icon">
              <HomeIcon type={opt.icon} />
            </span>
            <span className="home-card-label">{opt.label}</span>
            <span className="home-card-title">{opt.title}</span>
            <span className="home-card-desc muted">{opt.description}</span>
            {"online" in opt && opt.online && (
              <span className="home-card-tag">Requires internet</span>
            )}
            <span className="home-card-action">{opt.action}</span>
          </button>
        ))}
      </div>

      <section className="home-journey card" aria-labelledby="journey-title">
        <div className="section-heading">
          <h2 id="journey-title">Your archive journey</h2>
          <p className="muted">A guided path from raw media to a saved 3D archive.</p>
        </div>
        <ol className="journey-steps">
          {JOURNEY.map(([title, text], index) => (
            <li key={title}>
              <span className="journey-step-num">{index + 1}</span>
              <strong>{title}</strong>
              <span>{text}</span>
            </li>
          ))}
        </ol>
      </section>

      <div className="home-support-grid">
        <section className="capture-tips card">
          <h2>Capture tips</h2>
          <ul>
            {TIPS.map((tip) => (
              <li key={tip}>{tip}</li>
            ))}
          </ul>
        </section>

        <section className="local-status-card card">
          <h2>{online ? "Online features available" : "Local mode"}</h2>
          <p className="muted">{localStatus}</p>
          <p className="status-note">ArchiveSpace is designed to run from a USB stick and keep work local.</p>
        </section>

        <section className="recent-archives card">
          <div className="section-heading compact">
            <h2>Recent archives</h2>
            <button type="button" className="link-btn" onClick={() => navigate("/library")}>
              View all
            </button>
          </div>
          {recent.length > 0 ? (
            <ul>
              {recent.map((scene) => (
                <li key={scene.scene_id}>
                  <span>
                    <strong>{scene.title || "Untitled archive"}</strong>
                    <small>{inputTypeLabel(scene.source_type)}</small>
                  </span>
                  <FriendlyStatusMessage status={scene.status} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No saved archives yet. Create one when you are ready.</p>
          )}
        </section>
      </div>

      <section className="home-help card">
        <h2>How it works</h2>
        <p className="muted">
          ArchiveSpace is designed for galleries, museums, and university collections. It keeps the
          simple workflow first, while Advanced Mode adds technical details for DreamLab users.
        </p>
      </section>
    </div>
  );
}
