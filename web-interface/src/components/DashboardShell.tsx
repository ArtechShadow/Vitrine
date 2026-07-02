import { useEffect, useState, type CSSProperties } from "react";
import { Link, matchPath, NavLink, useLocation, useNavigate } from "react-router-dom";
import SceneList from "../pages/SceneList";
import SceneDetail from "../pages/SceneDetail";
import Pipeline from "../pages/Pipeline";
import Upload from "../pages/Upload";

function navClass({ isActive }: { isActive: boolean }) {
  return isActive ? "workspace-nav-link active" : "workspace-nav-link";
}

function stardate() {
  const now = new Date();
  const year = now.getFullYear();
  const start = new Date(year, 0, 0);
  const day = Math.floor((now.getTime() - start.getTime()) / 86400000);
  return `${year}.${String(day).padStart(3, "0")}`;
}

function WorkspaceEmpty() {
  return (
    <section className="workspace-empty" aria-label="Scene workspace">
      <div className="workspace-empty-scan" aria-hidden />
      <div className="workspace-empty-visual">
        <img src="/logo.jpg" alt="" />
      </div>
      <div>
        <p className="workspace-kicker">Preservation workspace</p>
        <h2>Select a scene to inspect the archive package</h2>
        <p className="muted">
          Review extracted frames, sparse reconstruction, Gaussian splat readiness,
          metadata, processing controls, and energy cost from one workspace.
        </p>
      </div>
    </section>
  );
}

function MotionColumns() {
  return (
    <div className="workspace-motion-columns" aria-hidden>
      {Array.from({ length: 10 }, (_, index) => (
        <span key={index} style={{ "--column-index": index } as CSSProperties} />
      ))}
    </div>
  );
}

export default function DashboardShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    const saved = window.localStorage.getItem("archivespace-theme");
    return saved === "light" ? "light" : "dark";
  });

  const sceneMatch = matchPath("/scenes/:sceneId", location.pathname);
  const sceneId = sceneMatch?.params.sceneId;
  const showPipeline = location.pathname === "/pipeline";
  const showUpload = location.pathname === "/upload";
  const showScene = !!sceneId;

  const close = () => navigate("/");
  const workspaceTitle = showPipeline
    ? "Processing pipeline"
    : showUpload
      ? "New capture"
      : showScene
        ? "Scene workspace"
        : "Scene workspace";
  const workspaceSubtitle = showPipeline
    ? "Video to frames to COLMAP to Gaussian splat"
    : showUpload
      ? "Upload a gallery walk-through"
      : showScene
        ? sceneId
    : "Select a capture from the library";

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("archivespace-theme", theme);
  }, [theme]);

  return (
    <div
      className={`dashboard-shell integrated-shell ${
        showScene || showPipeline || showUpload ? "workspace-has-detail" : "workspace-idle"
      }`}
    >
      <aside className="workspace-nav" aria-label="ArchiveSpace navigation">
        <Link to="/" className="workspace-brand">
          <img src="/logo.jpg" alt="" className="brand-logo" width={44} height={44} />
          <span>
            <strong>ArchiveSpace</strong>
            <small>Local preservation · {stardate()}</small>
          </span>
        </Link>
        <span className="app-status-badge workspace-status-badge">Work in progress</span>
        <nav>
          <NavLink to="/" end className={navClass}>
            Scenes
          </NavLink>
          <NavLink to="/pipeline" className={navClass}>
            Pipeline
          </NavLink>
          <span
            className="workspace-nav-link workspace-nav-link--disabled"
            aria-disabled="true"
            title="Immersive viewer is currently disabled"
          >
            Immersive viewer
          </span>
          <NavLink to="/upload" className={({ isActive }) => `${navClass({ isActive })} nav-cta`}>
            <span className="nav-cta-icon" aria-hidden>+</span>
            <span>New capture</span>
          </NavLink>
        </nav>
        <div className="workspace-nav-footer">
          <button
            type="button"
            className="theme-toggle"
            onClick={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          >
            {theme === "dark" ? "Light mode" : "Dark mode"}
          </button>
          <span className="footer-version">Protocol v4.20</span>
          <span className="muted">University of Salford x DreamLab</span>
        </div>
      </aside>

      <section className="workspace-library" aria-label="Scene library">
        <SceneList activeSceneId={sceneId} />
      </section>

      <section className="workspace-detail-panel" aria-label={workspaceTitle}>
        <MotionColumns />
        <header className="workspace-detail-header">
          <div>
            <p className="workspace-kicker">{workspaceTitle}</p>
            <h2>{workspaceSubtitle}</h2>
          </div>
          {(showPipeline || showUpload || showScene) && (
            <button type="button" className="workspace-close" onClick={close} aria-label="Close workspace">
              Close
            </button>
          )}
        </header>
        <div className="workspace-detail-scroll">
          {showPipeline ? <Pipeline embedded /> : null}
          {showUpload ? <Upload embedded onComplete={(id) => navigate(`/scenes/${id}`)} /> : null}
          {showScene && sceneId ? <SceneDetail sceneId={sceneId} embedded onClose={close} /> : null}
          {!showPipeline && !showUpload && !showScene ? <WorkspaceEmpty /> : null}
        </div>
      </section>
    </div>
  );
}
