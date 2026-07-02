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
  sourceUrl?: string;
  title?: string;
  sourceLabel?: string;
  immersive?: boolean;
  sceneScale?: [number, number, number];
  scenePosition?: [number, number, number];
  sceneRotation?: [number, number, number, number];
  sceneTransform?: Partial<SceneTransform> | null;
  enableWebXR?: boolean;
  cameraDistanceMultiplier?: number;
  environmentLabel?: string;
  onEnvironmentChange?: () => void;
}

type SplatViewerHandle = GaussianSplats3D.Viewer & {
  controls?: {
    target: { x: number; y: number; z: number; set?: (x: number, y: number, z: number) => void };
    enabled?: boolean;
    enableRotate?: boolean;
    enablePan?: boolean;
    enableZoom?: boolean;
    autoRotate?: boolean;
    autoRotateSpeed?: number;
    rotateSpeed?: number;
    zoomSpeed?: number;
    panSpeed?: number;
    minDistance?: number;
    maxDistance?: number;
    mouseButtons?: { LEFT?: number; MIDDLE?: number; RIGHT?: number };
    update: () => void;
    reset?: () => void;
    saveState?: () => void;
  };
  camera?: {
    position: {
      x: number;
      y: number;
      z: number;
      set?: (x: number, y: number, z: number) => void;
      copy?: (value: { x: number; y: number; z: number }) => void;
    };
    matrixWorld: { elements: number[] };
    up: { set?: (x: number, y: number, z: number) => void };
    lookAt?: (x: number, y: number, z: number) => void;
    updateProjectionMatrix?: () => void;
    updateMatrixWorld?: (force?: boolean) => void;
  };
  getSplatScene?: (sceneIndex: number) => {
    position?: { set?: (x: number, y: number, z: number) => void; x: number; y: number; z: number };
    quaternion?: { set?: (x: number, y: number, z: number, w: number) => void; x: number; y: number; z: number; w: number };
    scale?: { set?: (x: number, y: number, z: number) => void; x: number; y: number; z: number };
    updateTransform?: (dynamicMode?: boolean) => void;
  };
  getSceneCount?: () => number;
  forceRenderNextFrame?: () => void;
  update?: () => void;
};

type Orientation = "front" | "top" | "side";

const DEFAULT_SCENE_POSITION: [number, number, number] = [0, 0, 0];
const DEFAULT_SCENE_ROTATION: [number, number, number, number] = [1, 0, 0, 0];
const DEFAULT_VIEW_ZOOM = 3;

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

function scalePosition(position: [number, number, number], multiplier: number): [number, number, number] {
  const zoomedMultiplier = multiplier / DEFAULT_VIEW_ZOOM;
  return [position[0] * zoomedMultiplier, position[1] * zoomedMultiplier, position[2] * zoomedMultiplier];
}

function setVec3(
  target: { x: number; y: number; z: number; set?: (x: number, y: number, z: number) => void },
  value: [number, number, number],
) {
  if (target.set) target.set(value[0], value[1], value[2]);
  else {
    target.x = value[0];
    target.y = value[1];
    target.z = value[2];
  }
}

function setQuat(
  target: { x: number; y: number; z: number; w: number; set?: (x: number, y: number, z: number, w: number) => void },
  value: [number, number, number, number],
) {
  if (target.set) target.set(value[0], value[1], value[2], value[3]);
  else {
    target.x = value[0];
    target.y = value[1];
    target.z = value[2];
    target.w = value[3];
  }
}

function getScaleUnit(scale?: [number, number, number]) {
  return Math.max(0.001, ...(scale ?? [1, 1, 1]).map((value) => Math.abs(value)));
}

function getNavigationMultiplier(cameraDistanceMultiplier: number, sceneScale?: [number, number, number]) {
  const scaleUnit = getScaleUnit(sceneScale);
  const normalizedScale = scaleUnit < 1 ? Math.sqrt(scaleUnit) : scaleUnit;
  return cameraDistanceMultiplier * normalizedScale;
}

function applySplatSceneTransform(
  viewer: SplatViewerHandle | null,
  scenePosition: [number, number, number],
  sceneRotation: [number, number, number, number],
  sceneScale?: [number, number, number],
) {
  if (!viewer?.getSplatScene) return false;
  if (viewer.getSceneCount && viewer.getSceneCount() < 1) return false;

  let scene: ReturnType<NonNullable<SplatViewerHandle["getSplatScene"]>>;
  try {
    scene = viewer.getSplatScene(0);
  } catch {
    return false;
  }
  if (!scene) return;
  if (scene.position) setVec3(scene.position, scenePosition);
  if (scene.quaternion) setQuat(scene.quaternion, sceneRotation);
  if (scene.scale && sceneScale) setVec3(scene.scale, sceneScale);
  scene.updateTransform?.(false);
  viewer?.forceRenderNextFrame?.();
  viewer?.update?.();
  return true;
}

function isDisposedSceneError(error: unknown) {
  return (
    error instanceof Error &&
    (error.name === "AbortedPromiseError" || error.message.toLowerCase().includes("scene disposed"))
  );
}

function isDomNotFoundError(error: unknown) {
  return error instanceof DOMException && error.name === "NotFoundError";
}

function disposeViewer(viewer: GaussianSplats3D.Viewer, viewerRoot: HTMLDivElement) {
  viewerRoot.style.display = "none";
  if (viewerRoot.parentNode !== document.body) {
    document.body.appendChild(viewerRoot);
  }

  try {
    const disposeResult = (viewer as unknown as { dispose: () => unknown }).dispose();
    if (disposeResult && typeof (disposeResult as PromiseLike<void>).then === "function") {
      void Promise.resolve(disposeResult).catch((error: unknown) => {
        if (!isDisposedSceneError(error) && !isDomNotFoundError(error)) {
          console.error("Splat viewer cleanup failed", error);
        }
      });
    }
  } catch (error) {
    if (!isDisposedSceneError(error) && !isDomNotFoundError(error)) {
      console.error("Splat viewer cleanup failed", error);
    }
  }
}

export default function SplatViewer({
  sceneId,
  sourceUrl,
  title,
  sourceLabel,
  immersive = false,
  sceneScale,
  scenePosition = DEFAULT_SCENE_POSITION,
  sceneRotation = DEFAULT_SCENE_ROTATION,
  sceneTransform,
  enableWebXR = false,
  cameraDistanceMultiplier = 1,
  environmentLabel,
  onEnvironmentChange,
}: Props) {
  const rootRef = useRef<HTMLDivElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<GaussianSplats3D.Viewer | null>(null);
  const sceneLoadedRef = useRef(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<Orientation>("front");
  const appliedScenePosition = useMemo(
    () => (sceneTransform ? sceneTransformToPosition(sceneTransform) : scenePosition),
    [scenePosition, sceneTransform],
  );
  const appliedSceneRotation = useMemo(
    () => (sceneTransform ? sceneTransformToQuaternion(sceneTransform) : sceneRotation),
    [sceneRotation, sceneTransform],
  );
  const appliedSceneScale = useMemo(
    () => (sceneTransform ? sceneTransformToScale(sceneTransform) : sceneScale),
    [sceneScale, sceneTransform],
  );

  const orientCamera = useCallback((orientation: Orientation = "front") => {
    const viewer = viewerRef.current as SplatViewerHandle | null;
    if (!viewer?.camera || !viewer.controls) return;
    setViewMode(orientation);
    const next = ORIENTATIONS[orientation];
    setVec3(viewer.camera.position, scalePosition(next.position, getNavigationMultiplier(cameraDistanceMultiplier, appliedSceneScale)));
    if (viewer.camera.up?.set) viewer.camera.up.set(...next.up);
    setVec3(viewer.controls.target, [0, 0, 0]);
    viewer.camera.lookAt?.(0, 0, 0);
    viewer.camera.updateProjectionMatrix?.();
    viewer.camera.updateMatrixWorld?.(true);
    viewer.controls.update();
  }, [appliedSceneScale, cameraDistanceMultiplier]);

  const configureControls = useCallback((autoRotateEnabled: boolean) => {
    const viewer = viewerRef.current as SplatViewerHandle | null;
    if (!viewer?.controls) return;
    viewer.controls.enabled = true;
    viewer.controls.enableRotate = true;
    viewer.controls.enablePan = true;
    viewer.controls.enableZoom = true;
    const navigationMultiplier = getNavigationMultiplier(cameraDistanceMultiplier, appliedSceneScale);
    viewer.controls.rotateSpeed = 0.72;
    viewer.controls.zoomSpeed = Math.min(6, Math.max(1.45, 1.6 / navigationMultiplier));
    viewer.controls.panSpeed = 1.25;
    viewer.controls.mouseButtons = { LEFT: 0, MIDDLE: 2, RIGHT: 2 };
    viewer.controls.autoRotateSpeed = 0.7;
    viewer.controls.autoRotate = autoRotateEnabled;
    viewer.controls.minDistance = 0.0001 * navigationMultiplier;
    viewer.controls.maxDistance = 100000 * navigationMultiplier;
    viewer.controls.update();
  }, [appliedSceneScale, cameraDistanceMultiplier]);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    let disposed = false;
    let cameraTimer = 0;
    sceneLoadedRef.current = false;
    const viewerRoot = document.createElement("div");
    viewerRoot.className = "splat-library-root";
    root.appendChild(viewerRoot);

    setLoading(true);
    setLoadError(null);

    const webXRMode =
      enableWebXR && "WebXRMode" in GaussianSplats3D
        ? (GaussianSplats3D as typeof GaussianSplats3D & { WebXRMode: { VR: unknown } }).WebXRMode.VR
        : undefined;
    const viewer = new GaussianSplats3D.Viewer({
      rootElement: viewerRoot,
      cameraUp: ORIENTATIONS.front.up,
      initialCameraPosition: scalePosition(
        ORIENTATIONS.front.position,
        getNavigationMultiplier(cameraDistanceMultiplier, appliedSceneScale),
      ),
      initialCameraLookAt: [0, 0, 0],
      sharedMemoryForWorkers: false,
      gpuAcceleratedSort: false,
      ...(webXRMode ? { webXRMode } : {}),
    });
    viewerRef.current = viewer;

    const source = sourceUrl ?? (sceneId ? splatUrl(sceneId, "scene.ply") : null);
    if (!source) {
      setLoadError("No splat source configured.");
      setLoading(false);
      return () => {
        disposed = true;
        disposeViewer(viewer, viewerRoot);
        if (viewerRef.current === viewer) viewerRef.current = null;
      };
    }

    viewer
      .addSplatScene(source, {
        showLoadingUI: false,
        splatAlphaRemovalThreshold: 5,
        progressiveLoad: immersive,
        position: appliedScenePosition,
        rotation: appliedSceneRotation,
        ...(appliedSceneScale ? { scale: appliedSceneScale } : {}),
      })
      .then(() => {
        if (disposed) return;
        sceneLoadedRef.current = true;
        viewer.start();
        cameraTimer = window.setTimeout(() => {
          if (disposed) return;
          configureControls(false);
          orientCamera("front");
        }, 150);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (disposed && isDisposedSceneError(err)) return;
        console.error("Splat load failed", err);
        if (!disposed) {
          setLoadError("Failed to load splat - file may still be exporting or the asset is unavailable.");
          setLoading(false);
        }
      });

    return () => {
      disposed = true;
      sceneLoadedRef.current = false;
      window.clearTimeout(cameraTimer);
      disposeViewer(viewer, viewerRoot);
      if (viewerRef.current === viewer) viewerRef.current = null;
    };
  }, [appliedScenePosition, appliedSceneRotation, appliedSceneScale, cameraDistanceMultiplier, enableWebXR, immersive, sceneId, sourceUrl]);

  useEffect(() => {
    if (!sceneLoadedRef.current) return;
    const applied = applySplatSceneTransform(
      viewerRef.current as SplatViewerHandle | null,
      appliedScenePosition,
      appliedSceneRotation,
      appliedSceneScale,
    );
    if (!applied) return;
    configureControls(false);
    orientCamera("front");
  }, [appliedScenePosition, appliedSceneRotation, appliedSceneScale, configureControls, orientCamera]);

  return (
    <div
      ref={wrapRef}
      className={`preview-viewer splat-viewer-wrap ${immersive ? "splat-viewer-wrap--immersive" : ""}`}
    >
      {immersive ? (
        <button type="button" className="splat-environment-button" onClick={onEnvironmentChange}>
          Splat preview environment{environmentLabel ? `: ${environmentLabel}` : ""}
        </button>
      ) : (
        <div className="preview-toolbar">
          {title ? (
            <span className="preview-title">
              {title}
              {sourceLabel ? <small>{sourceLabel}</small> : null}
            </span>
          ) : (
            <span />
          )}
          <div className="preview-toolbar-actions">
            {loading && <span className="viewer-status-pill">Loading scene...</span>}
            <div className="viewer-segmented" role="group" aria-label="Camera view">
              {VIEW_ACTIONS.map((action) => (
                <button
                  key={action.id}
                  type="button"
                  onClick={() => orientCamera(action.id)}
                  className={viewMode === action.id ? "active" : ""}
                >
                  {action.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
      <div ref={rootRef} className="splat-canvas-host" />
      {loadError && <p className="muted preview-error">{loadError}</p>}
      <p className="muted preview-hint">
        {immersive
          ? "Drag to rotate - scroll to zoom - change the preview environment to reframe"
          : "Drag to rotate - middle-drag to pan - scroll to zoom - use Front, Top, or Side to change view"}
      </p>
    </div>
  );
}
