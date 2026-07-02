import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getBranches, type BranchInfo } from "../api/client";

const FLOW = [
  { id: "upload", label: "New capture", short: "Video" },
  { id: "ffmpeg", label: "FFmpeg", short: "Frames" },
  { id: "colmap", label: "COLMAP", short: "Sparse" },
  { id: "splat", label: "Splatfacto", short: "Splat" },
  { id: "viewer", label: "Viewers", short: "Browse" },
] as const;

const STEPS = [
  {
    id: "upload",
    n: 1,
    title: "New capture",
    tool: "ArchiveSpace ingest",
    icon: "film",
    status: "live" as const,
    summary:
      "Drag-and-drop or browse to upload a gallery walk-through. Source video is preserved; scene package is created under data/scenes/.",
    outputs: ["source/", "metadata/scene.json"],
  },
  {
    id: "ffmpeg",
    n: 2,
    title: "Frame extraction & QA",
    tool: "FFmpeg + Laplacian QA",
    icon: "frames",
    status: "live" as const,
    summary:
      "Frames extract at chosen FPS (default 2). QA scores blur and duplicates automatically — keep/remove animation plays in the background during analysis.",
    outputs: ["frames/", "metadata/qa_report.json", "metadata/qa_progress.json", "derivatives/contact_sheet.jpg"],
  },
  {
    id: "colmap",
    n: 3,
    title: "Sparse reconstruction",
    tool: "COLMAP + recovery",
    icon: "cloud",
    status: "live" as const,
    summary:
      "Structure-from-motion recovers poses and sparse geometry. Interactive 3D Scene Viewer, live progress, and automatic COLMAP recovery when registration is low.",
    outputs: ["colmap/sparse/0/", "sparse_preview.jpg", "sparse_points.json", "recovery_report.json"],
  },
  {
    id: "splat",
    n: 4,
    title: "Gaussian splat",
    tool: "Nerfstudio Splatfacto",
    icon: "splat",
    status: "live" as const,
    summary: "Trains the master preservation artefact — a navigable Gaussian splat from COLMAP output. Launch training from the scene page.",
    outputs: ["splat/scene.ply"],
  },
  {
    id: "viewer",
    n: 5,
    title: "Browser viewers",
    tool: "3D Scene Viewer · Gaussian Splats 3D",
    icon: "viewer",
    status: "live" as const,
    summary:
      "Preview sparse point clouds before scene building finishes. Full scene viewer with guided camera controls and a rendered contact sheet for review.",
    outputs: ["3D Scene Viewer", "Splat viewer", "Metadata editor"],
  },
] as const;

const LIVE_UI = [
  "Scene library — animated Gaussian splat background",
  "New capture — centered drag-and-drop upload with glass panels",
  "QA analysis — automatic keep/remove backdrop during scoring",
  "3D Scene Viewer - sparse cloud with guided camera controls",
  "LingBot preview tab — when worker model env is configured",
  "COLMAP recovery — auto trigger below 60% registration + manual retry",
  "Energy cost panel — live electricity estimates during jobs",
  "Processing controls — pause, resume, and cancel pipeline steps",
] as const;

const PACKAGE_TREE = [
  { at: "New capture", path: "source/ · metadata/scene.json" },
  { at: "FFmpeg + QA", path: "frames/ · metadata/qa_report.json · derivatives/contact_sheet.jpg" },
  { at: "COLMAP", path: "colmap/ · derivatives/sparse_points.json · sparse_preview.jpg" },
  { at: "Recovery", path: "metadata/recovery_report.json · derivatives/recovery_keyframes/" },
  { at: "Splatfacto", path: "splat/scene.ply" },
] as const;

const FUTURE = [
  {
    phase: "Near term",
    items: [
      { title: "Hotspots editor", desc: "Clickable annotations overlaid on the splat viewer", tag: "planned" },
      { title: "Scene package export", desc: "Zip and share complete scene folders from the UI", tag: "planned" },
      { title: "Auto frame cull", desc: "Apply QA keep/remove decisions to disk after review", tag: "planned" },
    ],
  },
  {
    phase: "Research",
    items: [
      { title: "LingBot-Map training hook", desc: "Wire fast preview into automatic pipeline after COLMAP", tag: "research" },
      { title: "PPiSP photometric correction", desc: "Exposure, vignetting, color, and camera-response compensation before radiance-field training", tag: "research" },
      { title: "SAM3 hotspots", desc: "Concept masks → isolated objects in the viewer", tag: "research" },
    ],
  },
  {
    phase: "Deployment",
    items: [
      { title: "Gallery kiosk mode", desc: "Exhibition viewer for Salford showcases", tag: "planned" },
      { title: "Docker GPU stack", desc: "Reproducible COLMAP + training environment", tag: "planned" },
      { title: "Optional mesh export", desc: "Unreal / mesh pipeline as experimental branch", tag: "experimental" },
    ],
  },
] as const;

function branchBadgeClass(status: string): string {
  if (status === "available" || status === "configured") return "pipe-branch-badge pipe-branch-badge--live";
  if (status === "partial" || status === "running") return "pipe-branch-badge pipe-branch-badge--partial";
  return "pipe-branch-badge";
}

function StepIcon({ type }: { type: string }) {
  switch (type) {
    case "film":
      return (
        <svg viewBox="0 0 24 24" aria-hidden className="pipe-icon-svg">
          <rect x="3" y="5" width="18" height="14" rx="2" fill="none" stroke="currentColor" strokeWidth="1.5" />
          <path d="M7 5v14M17 5v14M3 10h4M3 14h4M17 10h4M17 14h4" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      );
    case "frames":
      return (
        <svg viewBox="0 0 24 24" aria-hidden className="pipe-icon-svg">
          <rect x="3" y="3" width="7" height="7" rx="1" fill="currentColor" opacity="0.9" />
          <rect x="14" y="3" width="7" height="7" rx="1" fill="currentColor" opacity="0.6" />
          <rect x="3" y="14" width="7" height="7" rx="1" fill="currentColor" opacity="0.6" />
          <rect x="14" y="14" width="7" height="7" rx="1" fill="currentColor" opacity="0.35" />
        </svg>
      );
    case "cloud":
      return (
        <svg viewBox="0 0 24 24" aria-hidden className="pipe-icon-svg">
          {[4, 8, 12, 16, 20].map((x, i) =>
            [5, 10, 15, 19].map((y, j) => (
              <circle key={`${i}-${j}`} cx={x} cy={y} r="1.2" fill="currentColor" opacity={0.4 + ((i + j) % 3) * 0.2} />
            )),
          )}
        </svg>
      );
    case "splat":
      return (
        <svg viewBox="0 0 24 24" aria-hidden className="pipe-icon-svg">
          <circle cx="12" cy="12" r="3" fill="currentColor" />
          <circle cx="6" cy="8" r="1.5" fill="currentColor" opacity="0.7" />
          <circle cx="18" cy="9" r="2" fill="currentColor" opacity="0.5" />
          <circle cx="8" cy="17" r="1.8" fill="currentColor" opacity="0.6" />
          <circle cx="17" cy="16" r="1.2" fill="currentColor" opacity="0.8" />
        </svg>
      );
    default:
      return (
        <svg viewBox="0 0 24 24" aria-hidden className="pipe-icon-svg">
          <rect x="3" y="5" width="18" height="13" rx="2" fill="none" stroke="currentColor" strokeWidth="1.5" />
          <circle cx="12" cy="11.5" r="3" fill="currentColor" opacity="0.5" />
        </svg>
      );
  }
}

function FlowIcon({ id }: { id: string }) {
  const step = STEPS.find((s) => s.id === id);
  return step ? <StepIcon type={step.icon} /> : null;
}

interface PipelineProps {
  embedded?: boolean;
}

export default function Pipeline({ embedded }: PipelineProps = {}) {
  const [branches, setBranches] = useState<BranchInfo[]>([]);
  const [branchesLoading, setBranchesLoading] = useState(true);

  useEffect(() => {
    getBranches()
      .then(setBranches)
      .catch(() => setBranches([]))
      .finally(() => setBranchesLoading(false));
  }, []);

  return (
    <div className={`pipeline-page ${embedded ? "pipeline-page--embedded" : ""}`}>
      {!embedded && (
        <div className="page-title">
          <h1>Processing pipeline</h1>
          <p>
            From gallery video to navigable Gaussian splat — local-first, all data under{" "}
            <code>data/scenes/</code>.
          </p>
        </div>
      )}

      <section className="pipe-hero card" aria-label="Pipeline overview">
        <div className="pipe-hero-track">
          {FLOW.map((node, i) => (
            <div key={node.id} className="pipe-hero-segment">
              <div className={`pipe-hero-node pipe-hero-node--${node.id}`}>
                <div className="pipe-hero-icon">
                  <FlowIcon id={node.id} />
                </div>
                <span className="pipe-hero-label">{node.label}</span>
                <span className="pipe-hero-short">{node.short}</span>
              </div>
              {i < FLOW.length - 1 && <div className="pipe-hero-connector" aria-hidden />}
            </div>
          ))}
        </div>
        <p className="pipe-hero-caption muted">
          Gaussian splats are the <strong>master artefact</strong> — source video is always preserved.
        </p>
      </section>

      <div className="pipe-layout-split">
        <section className="pipe-package card" aria-label="Scene package">
          <h2 className="pipe-section-title">Scene package on disk</h2>
          <div className="pipe-tree">
            <div className="pipe-tree-root">data/scenes/&lt;scene_id&gt;/</div>
            <div className="pipe-tree-branches">
              {PACKAGE_TREE.map((row) => (
                <div key={row.at} className="pipe-tree-row">
                  <span className="pipe-tree-stage">{row.at}</span>
                  <span className="pipe-tree-line" aria-hidden />
                  <code className="pipe-tree-path">{row.path}</code>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="pipe-live-ui card" aria-label="Live UI">
          <h2 className="pipe-section-title">In the app today</h2>
          <ul className="pipe-live-list">
            {LIVE_UI.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      </div>

      <section aria-label="Pipeline steps">
        <h2 className="pipe-section-title pipe-steps-heading">Stages</h2>
        <div className="pipe-steps-grid">
          {STEPS.map((step) => (
            <article key={step.id} className={`card pipe-step-card pipe-step-card--${step.id}`}>
              <div className="pipe-step-visual">
                <StepIcon type={step.icon} />
              </div>
              <div className="pipe-step-body">
                <div className="pipe-step-meta">
                  <span className="pipe-step-n">{step.n}</span>
                  <span className="pipe-step-badge">{step.status}</span>
                </div>
                <h3>{step.title}</h3>
                <p className="pipe-step-tool">{step.tool}</p>
                <p className="pipe-step-summary">{step.summary}</p>
                <div className="pipe-output-pills">
                  {step.outputs.map((o) => (
                    <span key={o} className="pipe-output-pill">
                      {o}
                    </span>
                  ))}
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="pipe-branches card" aria-label="Branches">
        <h2 className="pipe-section-title">Branches & experiments</h2>
        <p className="muted text-sm">
          Core path above is required for splat training. Recovery and optional tools run when needed or configured.
        </p>
        {branchesLoading ? (
          <p className="muted text-sm">Loading branch status…</p>
        ) : branches.length === 0 ? (
          <p className="muted text-sm">Branch status unavailable — start the API worker to see live configuration.</p>
        ) : (
          <div className="pipe-branch-grid">
            {branches.map((b) => (
              <div key={b.id} className="pipe-branch-card">
                <span className={branchBadgeClass(b.status)}>{b.status}</span>
                <h3>{b.name}</h3>
                <p>{b.purpose}</p>
                {b.install_doc && <p className="pipe-branch-doc muted text-xs">{b.install_doc}</p>}
              </div>
            ))}
          </div>
        )}
      </section>

      <details className="pipe-future-details card">
        <summary className="pipe-future-summary">Future goals · research roadmap</summary>
        <div className="pipe-future-grid">
          {FUTURE.map((group) => (
            <div key={group.phase} className="pipe-future-col">
              <h3 className="pipe-future-phase">{group.phase}</h3>
              <ul className="pipe-future-list">
                {group.items.map((item) => (
                  <li key={item.title} className="pipe-future-item">
                    <div className="pipe-future-item-head">
                      <strong>{item.title}</strong>
                      <span className={`pipe-tag pipe-tag--${item.tag}`}>{item.tag}</span>
                    </div>
                    <p>{item.desc}</p>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </details>

      {!embedded && (
        <p className="muted pipeline-cta">
          <Link to="/upload">New capture</Link> · <Link to="/">Scene library</Link>
        </p>
      )}
    </div>
  );
}
