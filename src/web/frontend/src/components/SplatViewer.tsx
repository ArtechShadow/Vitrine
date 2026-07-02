// 3D Gaussian-splat viewer.
//
// Harvested from PR #6's SplatViewer and rewritten to point at OUR splat
// endpoint (/api/scenes/<id>/splat/<file>, same-origin). Crucially it runs with
// `sharedMemoryForWorkers: false` and `gpuAcceleratedSort: false` so the page
// needs NO SharedArrayBuffer and therefore NO COOP/COEP headers on the loopback
// server. Consumes .ksplat / .ply / .splat (our web deliverable is .ksplat).

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as GaussianSplats3D from "@mkkellogg/gaussian-splats-3d";
import { splatUrl } from "../api/client";
import {
  sceneTransformToPosition,
  sceneTransformToQuaternion,
  sceneTransformToScale,
  type SceneTransform,
} from "../lib/sceneTransform";

interface Props {
  sceneId?: string;
  /** Splat file within the scene (default our web deliverable). */
  splatFile?: string;
  /** Explicit source (used for the demo/empty-state sample). Overrides sceneId. */
  sourceUrl?: string;
  title?: string;
  immersive?: boolean;
  sceneTransform?: Partial<SceneTransform> | null;
}

type Orientation = "front" | "top" | "side";

interface Vec3Like {
  x: number;
  y: number;
  z: number;
  set?: (x: number, y: number, z: number) => void;
}
interface Quat extends Vec3Like {
  w: number;
  set?: (x: number, y: number, z: number, w?: number) => void;
}

interface ViewerHandle {
  controls?: {
    target: Vec3Like;
    enabled?: boolean;
    enableRotate?: boolean;
    enablePan?: boolean;
    enableZoom?: boolean;
    rotateSpeed?: number;
    zoomSpeed?: number;
    panSpeed?: number;
    minDistance?: number;
    maxDistance?: number;
    mouseButtons?: { LEFT?: number; MIDDLE?: number; RIGHT?: number };
    update: () => void;
  };
  camera?: {
    position: Vec3Like;
    up: { set?: (x: number, y: number, z: number) => void };
    lookAt?: (x: number, y: number, z: number) => void;
    updateProjectionMatrix?: () => void;
    updateMatrixWorld?: (force?: boolean) => void;
  };
  getSplatScene?: (i: number) => { position?: Vec3Like; quaternion?: Quat; scale?: Vec3Like; updateTransform?: (d?: boolean) => void } | null;
  getSceneCount?: () => number;
  forceRenderNextFrame?: () => void;
  update?: () => void;
}

const ORIENTATIONS: Record<Orientation, { position: [number, number, number]; up: [number, number, number] }> = {
  front: { position: [0, 1.35, 2.85], up: [0, 1, 0] },
  top: { position: [0, 3.35, 0.15], up: [0, 0, -1] },
  side: { position: [3.05, 1.15, 0], up: [0, 1, 0] },
};

const VIEW_ACTIONS: { id: Orientation; label: string }[] = [
  { id: "front", label: "Front" },
  { id: "top", label: "Top" },
  { id: "side", label: "Side" },
];

function setVec3(target: Vec3Like, value: [number, number, number]) {
  if (target.set) target.set(value[0], value[1], value[2]);
  else {
    target.x = value[0];
    target.y = value[1];
    target.z = value[2];
  }
}

function isDisposedSceneError(error: unknown): boolean {
  return (
    error instanceof Error &&
    (error.name === "AbortedPromiseError" || error.message.toLowerCase().includes("scene disposed"))
  );
}

function isDomNotFoundError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "NotFoundError";
}

function disposeViewer(viewer: GaussianSplats3D.Viewer, host: HTMLElement) {
  host.style.display = "none";
  if (host.parentNode !== document.body) document.body.appendChild(host);
  try {
    const result = viewer.dispose();
    if (result && typeof (result as PromiseLike<void>).then === "function") {
      void Promise.resolve(result).catch((err: unknown) => {
        if (!isDisposedSceneError(err) && !isDomNotFoundError(err)) console.error("Splat cleanup failed", err);
      });
    }
  } catch (err) {
    if (!isDisposedSceneError(err) && !isDomNotFoundError(err)) console.error("Splat cleanup failed", err);
  }
  host.remove();
}

export default function SplatViewer({
  sceneId,
  splatFile = "scene.ksplat",
  sourceUrl,
  title,
  immersive = false,
  sceneTransform,
}: Props) {
  const rootRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<GaussianSplats3D.Viewer | null>(null);
  const loadedRef = useRef(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<Orientation>("front");

  const position = useMemo(() => sceneTransformToPosition(sceneTransform), [sceneTransform]);
  const rotation = useMemo(() => sceneTransformToQuaternion(sceneTransform), [sceneTransform]);
  const scale = useMemo(() => sceneTransformToScale(sceneTransform), [sceneTransform]);

  const source = sourceUrl ?? (sceneId ? splatUrl(sceneId, splatFile) : null);

  const orientCamera = useCallback((orientation: Orientation) => {
    const viewer = viewerRef.current as unknown as ViewerHandle | null;
    if (!viewer?.camera || !viewer.controls) return;
    setViewMode(orientation);
    const next = ORIENTATIONS[orientation];
    setVec3(viewer.camera.position, next.position);
    viewer.camera.up.set?.(next.up[0], next.up[1], next.up[2]);
    setVec3(viewer.controls.target, [0, 0, 0]);
    viewer.camera.lookAt?.(0, 0, 0);
    viewer.camera.updateProjectionMatrix?.();
    viewer.camera.updateMatrixWorld?.(true);
    viewer.controls.update();
  }, []);

  const configureControls = useCallback(() => {
    const viewer = viewerRef.current as unknown as ViewerHandle | null;
    if (!viewer?.controls) return;
    const c = viewer.controls;
    c.enabled = true;
    c.enableRotate = true;
    c.enablePan = true;
    c.enableZoom = true;
    c.rotateSpeed = 0.72;
    c.zoomSpeed = 1.6;
    c.panSpeed = 1.25;
    c.mouseButtons = { LEFT: 0, MIDDLE: 2, RIGHT: 2 };
    c.update();
  }, []);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    let disposed = false;
    let cameraTimer = 0;
    loadedRef.current = false;
    setLoading(true);
    setLoadError(null);

    const host = document.createElement("div");
    host.className = "splat-canvas-root";
    root.appendChild(host);

    const viewer = new GaussianSplats3D.Viewer({
      rootElement: host,
      cameraUp: ORIENTATIONS.front.up,
      initialCameraPosition: ORIENTATIONS.front.position,
      initialCameraLookAt: [0, 0, 0],
      // No SharedArrayBuffer → no COOP/COEP required on the loopback server.
      sharedMemoryForWorkers: false,
      gpuAcceleratedSort: false,
    });
    viewerRef.current = viewer;

    if (!source) {
      setLoadError("No splat available yet.");
      setLoading(false);
      return () => {
        disposed = true;
        disposeViewer(viewer, host);
        if (viewerRef.current === viewer) viewerRef.current = null;
      };
    }

    viewer
      .addSplatScene(source, {
        showLoadingUI: false,
        splatAlphaRemovalThreshold: 5,
        progressiveLoad: immersive,
        position,
        rotation,
        scale,
      })
      .then(() => {
        if (disposed) return;
        loadedRef.current = true;
        viewer.start();
        cameraTimer = window.setTimeout(() => {
          if (disposed) return;
          configureControls();
          orientCamera("front");
        }, 150);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (disposed && isDisposedSceneError(err)) return;
        console.error("Splat load failed", err);
        if (!disposed) {
          setLoadError("This splat could not be loaded — it may still be exporting.");
          setLoading(false);
        }
      });

    return () => {
      disposed = true;
      loadedRef.current = false;
      window.clearTimeout(cameraTimer);
      disposeViewer(viewer, host);
      if (viewerRef.current === viewer) viewerRef.current = null;
    };
  }, [source, immersive, position, rotation, scale, configureControls, orientCamera]);

  return (
    <div className={`splat-viewer ${immersive ? "splat-viewer--immersive" : ""}`}>
      {!immersive && (
        <div className="splat-toolbar">
          <span className="splat-title">{title ?? "3D scene"}</span>
          <div className="splat-toolbar-actions">
            {loading && <span className="viewer-pill">Loading…</span>}
            <div className="segmented" role="group" aria-label="Camera view">
              {VIEW_ACTIONS.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  className={viewMode === a.id ? "active" : ""}
                  onClick={() => orientCamera(a.id)}
                  disabled={loading || !!loadError}
                >
                  {a.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
      <div ref={rootRef} className="splat-canvas-host" />
      {loadError && <p className="muted splat-error">{loadError}</p>}
      {!loadError && (
        <p className="muted splat-hint">
          {immersive
            ? "Drag to rotate · scroll to zoom"
            : "Drag to rotate · middle-drag to pan · scroll to zoom · Front / Top / Side to reframe"}
        </p>
      )}
    </div>
  );
}
