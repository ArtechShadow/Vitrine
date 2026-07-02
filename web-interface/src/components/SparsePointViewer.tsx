import { useCallback, useEffect, useRef, useState } from "react";
import ImageLightbox from "./ImageLightbox";
import PreviewPlaceholder from "./PreviewPlaceholder";
import { transformPoint, type SceneTransform } from "../lib/sceneTransform";
import { isPreviewMode } from "../lib/previewMode";

interface Point {
  position: [number, number, number];
  color: [number, number, number];
}

interface CloudBounds {
  cx: number;
  cy: number;
  cz: number;
  radius: number;
}

interface Props {
  sceneId: string;
  fallbackImageUrl?: string;
  sparseReady?: boolean;
  processing?: boolean;
  sceneTransform?: Partial<SceneTransform> | null;
}

const DEFAULT_ZOOM = 3;
const ZOOM_MIN = 0.02;
const ZOOM_MAX = 80;
const ZOOM_STEP = 0.5;
const DEFAULT_YAW = 0.6;
const DEFAULT_PITCH = 0.35;
const FRAME_FILL = 0.82;
const PAN_SPEED = 1.15;

function computeBounds(points: Point[]): CloudBounds {
  const xs = points.map((p) => p.position[0]);
  const ys = points.map((p) => p.position[1]);
  const zs = points.map((p) => p.position[2]);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  const cz = (Math.min(...zs) + Math.max(...zs)) / 2;
  let radius = 0;
  for (const p of points) {
    const dx = p.position[0] - cx;
    const dy = p.position[1] - cy;
    const dz = p.position[2] - cz;
    radius = Math.max(radius, Math.hypot(dx, dy, dz));
  }
  return { cx, cy, cz, radius: Math.max(radius, 0.01) };
}

export default function SparsePointViewer({
  sceneId,
  fallbackImageUrl,
  sparseReady = false,
  processing = false,
  sceneTransform,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const canvasWrapRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [points, setPoints] = useState<Point[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [fallbackFailed, setFallbackFailed] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [zoom, setZoom] = useState(DEFAULT_ZOOM);
  const rotRef = useRef({ yaw: DEFAULT_YAW, pitch: DEFAULT_PITCH });
  const panRef = useRef({ x: 0, y: 0 });
  const zoomRef = useRef(DEFAULT_ZOOM);
  const boundsRef = useRef<CloudBounds | null>(null);
  const dragRef = useRef({ x: 0, y: 0 });
  const dragModeRef = useRef<"rotate" | "pan">("rotate");

  useEffect(() => {
    zoomRef.current = zoom;
  }, [zoom]);

  useEffect(() => {
    if (!sparseReady) {
      setPoints([]);
      boundsRef.current = null;
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    setFallbackFailed(false);

    const load = async (attempt = 0): Promise<void> => {
      try {
        const r = await fetch(
          isPreviewMode ? "/demo/sparse-points.json" : `/api/scenes/${sceneId}/sparse-points`,
        );
        if (!r.ok) {
          if (attempt < 8 && !cancelled) {
            await new Promise((resolve) => window.setTimeout(resolve, 1500));
            return load(attempt + 1);
          }
          throw new Error("sparse-points unavailable");
        }
        const d = (await r.json()) as { points?: Point[] };
        if (cancelled) return;
        const loaded = d.points ?? [];
        const rawBounds = loaded.length ? computeBounds(loaded) : null;
        const transformed = rawBounds
          ? loaded.map((point) => ({
              ...point,
              position: transformPoint(point.position, sceneTransform, [
                rawBounds.cx,
                rawBounds.cy,
                rawBounds.cz,
              ]),
            }))
          : loaded;
        setPoints(transformed);
        boundsRef.current = transformed.length ? computeBounds(transformed) : null;
        if (!loaded.length) setError("Point cloud not ready");
      } catch {
        if (!cancelled) setError("Point cloud not ready");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [sceneId, sceneTransform, sparseReady]);

  useEffect(() => {
    setFallbackFailed(false);
  }, [fallbackImageUrl]);

  const adjustZoom = useCallback((delta: number) => {
    setZoom((z) => Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, +(z + delta).toFixed(2))));
  }, []);

  const handleWheel = useCallback(
    (event: React.WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();
      adjustZoom(event.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP);
    },
    [adjustZoom],
  );

  useEffect(() => {
    if (!points.length || !canvasRef.current || !boundsRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const bounds = boundsRef.current;
    let anim = 0;

    const draw = () => {
      const rect = canvas.getBoundingClientRect();
      const w = Math.max(1, Math.floor(rect.width));
      const h = Math.max(1, Math.floor(rect.height));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }

      const bg =
        getComputedStyle(document.documentElement).getPropertyValue("--bg").trim() || "#09090b";
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, w, h);

      const { yaw, pitch } = rotRef.current;
      const { x: panX, y: panY } = panRef.current;
      const cyR = Math.cos(yaw), syR = Math.sin(yaw);
      const cp = Math.cos(pitch), sp = Math.sin(pitch);
      const zoomLevel = zoomRef.current;

      const fitAxis = Math.min(w, h) * FRAME_FILL;
      const scale = (fitAxis * zoomLevel) / (bounds.radius * 2.15);

      const projected: { x: number; y: number; z: number; color: [number, number, number] }[] = [];
      for (const p of points) {
        const x = p.position[0] - bounds.cx;
        const y = p.position[1] - bounds.cy;
        const z = p.position[2] - bounds.cz;
        const x1 = x * cyR + z * syR;
        const z1 = -x * syR + z * cyR;
        const y1 = y * cp - z1 * sp;
        const z2 = y * sp + z1 * cp;
        projected.push({
          x: w / 2 + x1 * scale + panX,
          y: h / 2 - y1 * scale + panY,
          z: z2,
          color: p.color,
        });
      }
      projected.sort((a, b) => a.z - b.z);

      const pointSize = zoomLevel >= 1.5 ? 2 : zoomLevel <= 0.6 ? 1 : 2;
      for (const p of projected) {
        const depth = 0.4 + 0.6 * (1 / (1 + Math.exp(-p.z * 0.5)));
        const [r, g, b] = p.color;
        ctx.fillStyle = `rgb(${Math.floor(r * depth)},${Math.floor(g * depth)},${Math.floor(b * depth)})`;
        ctx.fillRect(p.x, p.y, pointSize, pointSize);
      }

      anim = requestAnimationFrame(draw);
    };
    draw();
    return () => cancelAnimationFrame(anim);
  }, [points, dragging]);

  function onPointerDown(e: React.PointerEvent) {
    e.preventDefault();
    setDragging(true);
    dragModeRef.current = e.button === 1 ? "pan" : "rotate";
    dragRef.current = { x: e.clientX, y: e.clientY };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }

  function onPointerMove(e: React.PointerEvent) {
    if (!dragging) return;
    const dx = e.clientX - dragRef.current.x;
    const dy = e.clientY - dragRef.current.y;
    dragRef.current = { x: e.clientX, y: e.clientY };
    if (dragModeRef.current === "pan") {
      panRef.current.x += dx * PAN_SPEED;
      panRef.current.y += dy * PAN_SPEED;
      return;
    }
    rotRef.current.yaw += dx * 0.008;
    rotRef.current.pitch += dy * 0.008;
  }

  function onPointerUp(e: React.PointerEvent) {
    setDragging(false);
    try {
      (e.target as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
  }

  const showPlaceholder =
    loading ||
    fallbackFailed ||
    (!points.length && (!fallbackImageUrl || !sparseReady));

  const placeholderMessage = loading
    ? "Loading 3D preview…"
    : processing
      ? "Sparse reconstruction in progress…"
      : "3D Scene Viewer not ready yet";

  const placeholderHint = processing
    ? "COLMAP is building the point cloud — this updates when complete."
    : sparseReady
      ? "Point data is still syncing — try refresh in a moment."
      : "Run COLMAP after frame extraction to generate the interactive preview.";

  if (showPlaceholder) {
    return (
      <div className="preview-viewer">
        <PreviewPlaceholder message={placeholderMessage} hint={placeholderHint} />
      </div>
    );
  }

  if (error && fallbackImageUrl && sparseReady) {
    return (
      <div className="preview-viewer">
      <div className="preview-toolbar">
          <span className="muted">Static preview (point cloud unavailable)</span>
      </div>
        <button type="button" className="preview-clickable" onClick={() => setLightboxOpen(true)}>
          <img
            src={fallbackImageUrl}
            alt="Sparse reconstruction preview"
            className="preview-image"
            onError={() => setFallbackFailed(true)}
          />
        </button>
        <ImageLightbox
          src={fallbackImageUrl}
          alt="Sparse reconstruction preview"
          open={lightboxOpen}
          onClose={() => setLightboxOpen(false)}
        />
      </div>
    );
  }

  return (
    <div ref={containerRef} className="preview-viewer sparse-viewer">
      <div className="preview-toolbar">
        <span className="muted">{points.length.toLocaleString()} sparse points</span>
        <div className="preview-toolbar-actions">
          <button type="button" onClick={() => adjustZoom(-ZOOM_STEP)} title="Zoom out">
            −
          </button>
          <span className="sparse-zoom-label">{Math.round((zoom / DEFAULT_ZOOM) * 100)}%</span>
          <button type="button" onClick={() => adjustZoom(ZOOM_STEP)} title="Zoom in">
            +
          </button>
        </div>
      </div>
      <div ref={canvasWrapRef} className="sparse-canvas-wrap" onWheel={handleWheel}>
        <canvas
          ref={canvasRef}
          className="sparse-canvas"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onAuxClick={(event) => event.preventDefault()}
        />
      </div>
      <p className="muted preview-hint">
        Drag to rotate - middle-drag to pan - scroll or use +/- to zoom
      </p>
      {fallbackImageUrl && (
        <ImageLightbox
          src={fallbackImageUrl}
          alt="Sparse reconstruction preview"
          open={lightboxOpen}
          onClose={() => setLightboxOpen(false)}
        />
      )}
    </div>
  );
}
