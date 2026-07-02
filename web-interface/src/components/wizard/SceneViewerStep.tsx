import SplatViewer from "../SplatViewer";
import SparsePointViewer from "../SparsePointViewer";
import type { SceneMetadata } from "../../api/client";
import { useAppMode } from "../../context/AppModeContext";

interface SceneViewerStepProps {
  sceneId: string;
  metadata: SceneMetadata | null;
}

export default function SceneViewerStep({ sceneId, metadata }: SceneViewerStepProps) {
  const { advancedMode } = useAppMode();
  const hasSplat = metadata?.status === "ready" || !!metadata?.outputs?.splat;
  const hasSparse = metadata?.status === "colmap_ready" || metadata?.status === "ready";

  return (
    <div className="wizard-step-panel wizard-step-panel--viewer">
      <h2>View your 3D scene</h2>
      <p className="muted">
        {hasSplat
          ? "Explore the archive you created. Drag to look around."
          : hasSparse
            ? "Your scene is still building. Here is a preview of the camera tracking so far."
            : "Your scene will appear here once processing finishes."}
      </p>

      <div className="wizard-viewer-frame card">
        {hasSplat ? (
          <SplatViewer sceneId={sceneId} sceneTransform={metadata?.sceneTransform} />
        ) : hasSparse ? (
          <SparsePointViewer sceneId={sceneId} sparseReady sceneTransform={metadata?.sceneTransform} />
        ) : (
          <div className="viewer-placeholder muted">Waiting for your 3D scene…</div>
        )}
      </div>

      {advancedMode && metadata && (
        <details className="advanced-panel card">
          <summary>Scene metadata</summary>
          <pre className="log-tail">{JSON.stringify(metadata, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}
