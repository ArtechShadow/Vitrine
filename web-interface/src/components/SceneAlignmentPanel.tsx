import { useEffect, useMemo, useRef, useState } from "react";
import {
  sparsePreviewUrl,
  splatPathUrl,
  updateMetadata,
  type SceneMetadata,
} from "../api/client";
import { useAppMode } from "../context/AppModeContext";
import {
  DEFAULT_SCENE_TRANSFORM,
  normalizeSceneTransform,
  sceneTransformToMatrix,
  type SceneTransform,
} from "../lib/sceneTransform";
import SparsePointViewer from "./SparsePointViewer";
import SplatViewer from "./SplatViewer";

interface SceneAlignmentPanelProps {
  sceneId: string;
  metadata: SceneMetadata | null;
  onSaved?: (metadata: SceneMetadata) => void;
}

export default function SceneAlignmentPanel({ sceneId, metadata, onSaved }: SceneAlignmentPanelProps) {
  const { advancedMode } = useAppMode();
  const [draft, setDraft] = useState<SceneTransform>(() =>
    normalizeSceneTransform(metadata?.sceneTransform),
  );
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDraft(normalizeSceneTransform(metadata?.sceneTransform));
  }, [metadata?.sceneTransform]);

  const cacheBust = metadata?.updated_at ?? "";
  const splatPath = metadata?.outputs?.splat || metadata?.splat?.path || "";
  const splatUrl = splatPath ? splatPathUrl(sceneId, splatPath) + `?t=${cacheBust}` : "";
  const sparseReady = !!(
    metadata?.outputs?.sparse_preview ||
    metadata?.status === "colmap_ready" ||
    metadata?.status === "ready"
  );
  const sparseUrl = sparsePreviewUrl(sceneId) + `?t=${cacheBust}`;

  const matrix = useMemo(() => sceneTransformToMatrix(draft), [draft]);

  function updateRotation(axis: keyof SceneTransform["rotationDeg"], delta: number) {
    setDraft((current) => ({
      ...current,
      rotationDeg: {
        ...current.rotationDeg,
        [axis]: current.rotationDeg[axis] + delta,
      },
    }));
  }

  function setNumeric(
    group: "rotationDeg" | "position",
    axis: "x" | "y" | "z",
    value: number,
  ) {
    setDraft((current) => ({
      ...current,
      [group]: {
        ...current[group],
        [axis]: Number.isFinite(value) ? value : 0,
      },
    }));
  }

  function applyPreset(preset: Partial<SceneTransform>) {
    setDraft((current) => normalizeSceneTransform({ ...current, ...preset }));
  }

  async function saveAlignment() {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await updateMetadata(sceneId, { sceneTransform: draft });
      setMessage("Alignment saved.");
      onSaved?.(saved);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save alignment");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="alignment-workflow">
      <div className="alignment-intro card">
        <div>
          <h2>Alignment</h2>
          <p className="muted">
            ArchiveSpace needs to know which way is up. Use these controls to make the scene face
            the right way, then save.
          </p>
        </div>
        <button type="button" className="primary" onClick={saveAlignment} disabled={saving}>
          {saving ? "Saving..." : advancedMode ? "Save transform to scene metadata" : "Save alignment"}
        </button>
      </div>

      <div className="alignment-layout">
        <div className="alignment-preview card">
          {splatUrl ? (
            <SplatViewer
              sceneId={sceneId}
              sourceUrl={splatUrl}
              title="Alignment preview"
              sourceLabel="Saved as metadata only"
              sceneTransform={draft}
            />
          ) : sparseReady ? (
            <SparsePointViewer
              sceneId={sceneId}
              fallbackImageUrl={sparseUrl}
              sparseReady={sparseReady}
              sceneTransform={draft}
            />
          ) : (
            <div className="viewer-placeholder muted">Camera tracking preview will appear here.</div>
          )}
          {advancedMode && (
            <div className="alignment-viewer-gizmo">
              <RotationGizmo
                rotation={draft.rotationDeg}
                onRotate={(axis, delta) => updateRotation(axis, delta)}
                onSetRotation={(axis, value) => setNumeric("rotationDeg", axis, value)}
              />
            </div>
          )}
        </div>

        <div className="alignment-controls card">
          <div className="alignment-simple-controls">
            <button type="button" onClick={() => applyPreset({ rotationDeg: { x: -90, y: 0, z: 0 } })}>
              Make upright
            </button>
            <button type="button" onClick={() => updateRotation("z", -90)}>
              Rotate left
            </button>
            <button type="button" onClick={() => updateRotation("z", 90)}>
              Rotate right
            </button>
            <button type="button" onClick={() => updateRotation("z", 180)}>
              Flip
            </button>
            <button type="button" onClick={() => setDraft(DEFAULT_SCENE_TRANSFORM)}>
              Reset
            </button>
          </div>

          {advancedMode && (
            <details className="advanced-panel alignment-advanced" open>
              <summary>Technical alignment controls</summary>
              <div className="alignment-number-grid">
                {(["x", "y", "z"] as const).map((axis) => (
                  <label key={`r-${axis}`}>
                    Rotation {axis.toUpperCase()}
                    <input
                      type="number"
                      value={draft.rotationDeg[axis]}
                      onChange={(e) => setNumeric("rotationDeg", axis, Number(e.target.value))}
                    />
                  </label>
                ))}
                <label>
                  Scale
                  <input
                    type="number"
                    min="0.01"
                    step="0.01"
                    value={draft.scale}
                    onChange={(e) =>
                      setDraft((current) => ({ ...current, scale: Math.max(0.01, Number(e.target.value) || 1) }))
                    }
                  />
                </label>
                {(["x", "y", "z"] as const).map((axis) => (
                  <label key={`p-${axis}`}>
                    Position {axis.toUpperCase()}
                    <input
                      type="number"
                      step="0.01"
                      value={draft.position[axis]}
                      onChange={(e) => setNumeric("position", axis, Number(e.target.value))}
                    />
                  </label>
                ))}
              </div>
              <label className="alignment-checkbox">
                <input
                  type="checkbox"
                  checked={draft.center}
                  onChange={(e) => setDraft((current) => ({ ...current, center: e.target.checked }))}
                />
                Centre scene
              </label>
              <h4>Raw transform matrix</h4>
              <pre className="log-tail">{formatMatrix(matrix)}</pre>
            </details>
          )}

          {message && <p className="success-text">{message}</p>}
          {error && <p className="error-text">{error}</p>}
        </div>
      </div>
    </div>
  );
}

interface RotationGizmoProps {
  rotation: SceneTransform["rotationDeg"];
  onRotate: (axis: keyof SceneTransform["rotationDeg"], delta: number) => void;
  onSetRotation: (axis: keyof SceneTransform["rotationDeg"], value: number) => void;
}

function RotationGizmo({ rotation, onRotate, onSetRotation }: RotationGizmoProps) {
  const dragRef = useRef<{ x: number; y: number; startX: number; startY: number } | null>(null);

  function onPointerDown(event: React.PointerEvent<HTMLDivElement>) {
    dragRef.current = {
      x: event.clientX,
      y: event.clientY,
      startX: rotation.x,
      startY: rotation.y,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event: React.PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag) return;
    onSetRotation("y", Math.round(drag.startY + (event.clientX - drag.x) * 0.45));
    onSetRotation("x", Math.round(drag.startX - (event.clientY - drag.y) * 0.45));
  }

  function onPointerUp(event: React.PointerEvent<HTMLDivElement>) {
    dragRef.current = null;
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="rotation-gizmo-panel">
      <div
        className="rotation-gizmo-stage"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        role="application"
        aria-label="3D rotation gizmo"
      >
        <div
          className="rotation-gizmo-object"
          style={{
            transform: `rotateX(${rotation.x}deg) rotateY(${rotation.y}deg) rotateZ(${rotation.z}deg)`,
          }}
        >
          <span className="rotation-gizmo-ring rotation-gizmo-ring--x" />
          <span className="rotation-gizmo-ring rotation-gizmo-ring--y" />
          <span className="rotation-gizmo-ring rotation-gizmo-ring--z" />
          <span className="rotation-gizmo-cube">
            <span className="rotation-gizmo-face rotation-gizmo-face--front">Front</span>
            <span className="rotation-gizmo-face rotation-gizmo-face--back">Back</span>
            <span className="rotation-gizmo-face rotation-gizmo-face--right">Right</span>
            <span className="rotation-gizmo-face rotation-gizmo-face--left">Left</span>
            <span className="rotation-gizmo-face rotation-gizmo-face--top">Up</span>
            <span className="rotation-gizmo-face rotation-gizmo-face--bottom">Down</span>
          </span>
        </div>
      </div>

      <div className="rotation-gizmo-controls" aria-label="Rotation axis controls">
        {(["x", "y", "z"] as const).map((axis) => (
          <div key={axis} className={`rotation-axis-control rotation-axis-control--${axis}`}>
            <span>{axis.toUpperCase()}</span>
            <button type="button" onClick={() => onRotate(axis, -5)} aria-label={`Rotate ${axis} minus 5 degrees`}>
              -5
            </button>
            <strong>{Math.round(rotation[axis])}deg</strong>
            <button type="button" onClick={() => onRotate(axis, 5)} aria-label={`Rotate ${axis} plus 5 degrees`}>
              +5
            </button>
          </div>
        ))}
      </div>
      <p className="muted rotation-gizmo-hint">
        Drag the gizmo to adjust X/Y rotation. Use the axis buttons or numeric fields for exact values.
      </p>
    </div>
  );
}

function formatMatrix(matrix: number[]): string {
  return matrix
    .reduce<string[]>((rows, value, index) => {
      const row = Math.floor(index / 4);
      rows[row] = `${rows[row] ?? ""}${value.toFixed(4).padStart(10, " ")}`;
      return rows;
    }, [])
    .join("\n");
}
