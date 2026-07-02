import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import AdvancedModeToggle from "./AdvancedModeToggle";
import OfflineModeIndicator from "./OfflineModeIndicator";
import PreviewModeBanner from "./PreviewModeBanner";
import { useAppMode } from "../context/AppModeContext";
import { useTheme } from "../context/ThemeContext";
import { isPreviewMode } from "../lib/previewMode";

function navClass({ isActive }: { isActive: boolean }) {
  return isActive ? "app-nav-link active" : "app-nav-link";
}

export default function AppShell() {
  const location = useLocation();
  const { advancedMode } = useAppMode();
  const { theme, toggleTheme } = useTheme();
  const [menuOpen, setMenuOpen] = useState(false);

  const isImmersive = location.pathname === "/viewer";

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  if (isImmersive) {
    return <Outlet />;
  }

  return (
    <div className={`app-shell ${isPreviewMode ? "app-shell--preview" : ""}`}>
      <PreviewModeBanner />
      <header className="app-header">
        <div className="app-brand-row">
          <Link to="/" className="app-brand">
            <img src="/logo.jpg" alt="" width={36} height={36} />
            <span>
              <strong>ArchiveSpace</strong>
              <small>University of Salford</small>
            </span>
          </Link>
          <span className="app-status-badge">
            {isPreviewMode ? "UI preview" : "Work in progress"}
          </span>
          <button
            type="button"
            className="mobile-menu-toggle"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span aria-hidden />
            <span aria-hidden />
            <span aria-hidden />
          </button>
        </div>

        <nav className={`app-nav ${menuOpen ? "is-open" : ""}`} aria-label="Main">
          <NavLink to="/" end className={navClass}>
            Home
          </NavLink>
          <NavLink to="/library" className={navClass}>
            My archives
          </NavLink>
          <NavLink to="/create" className={({ isActive }) => `${navClass({ isActive })} nav-cta`}>
            New archive
          </NavLink>
          {advancedMode && (
            <>
              <NavLink to="/pipeline" className={navClass}>
                Process map
              </NavLink>
              {isPreviewMode ? (
                <NavLink to="/viewer" className={navClass}>
                  Immersive viewer
                </NavLink>
              ) : (
                <span
                  className="app-nav-link app-nav-link--disabled"
                  aria-disabled="true"
                  title="Immersive viewer is currently disabled"
                >
                  Immersive viewer
                </span>
              )}
            </>
          )}
        </nav>

        <div className="app-header-tools">
          <OfflineModeIndicator />
          <AdvancedModeToggle />
          <button
            type="button"
            className="appearance-toggle"
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            onClick={toggleTheme}
          >
            {theme === "dark" ? (
              <svg viewBox="0 0 24 24" aria-hidden>
                <circle cx="12" cy="12" r="4.5" />
                <path d="M12 2.5v2.2M12 19.3v2.2M4.6 4.6l1.6 1.6M17.8 17.8l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.6 19.4l1.6-1.6M17.8 6.2l1.6-1.6" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" aria-hidden>
                <path d="M20.2 15.4A8.2 8.2 0 0 1 8.6 3.8 8.8 8.8 0 1 0 20.2 15.4Z" />
              </svg>
            )}
          </button>
        </div>
      </header>

      <main className="app-main">
        <Outlet />
      </main>

      <footer className="app-footer muted">
        {isPreviewMode
          ? "ArchiveSpace UI preview · University of Salford"
          : "Cultural heritage preservation · Local-first · Works offline from USB"}
      </footer>
    </div>
  );
}
