// App chrome: top navigation + routed content outlet. Rewrite of PR #6's
// AppShell without the online/offline/theme/advanced-mode context stack — the
// Vitrine app is a single local surface behind an SSH tunnel.

import { NavLink, Outlet } from "react-router-dom";

const NAV = [
  { to: "/", label: "Home", end: true },
  { to: "/library", label: "My archives", end: false },
  { to: "/create", label: "Create", end: false },
  { to: "/pipeline", label: "Pipeline", end: false },
] as const;

export default function AppShell() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <NavLink to="/" className="app-brand">
          <span className="app-brand-mark" aria-hidden />
          Vitrine
        </NavLink>
        <nav className="app-nav" aria-label="Primary">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `app-nav-link ${isActive ? "active" : ""}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <span className="app-header-note muted">Local · loopback</span>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
