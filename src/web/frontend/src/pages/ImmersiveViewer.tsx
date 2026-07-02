// Full-screen immersive splat viewer (route /viewer). Reads ?scene=<id>; falls
// back to an optional committed demo splat (VITE_DEMO_SPLAT_URL) for the
// empty-state. Rendered outside the AppShell chrome.

import { useSearchParams, useNavigate } from "react-router-dom";
import SplatViewer from "../components/SplatViewer";

export default function ImmersiveViewer() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const sceneId = params.get("scene");
  const splatFile = params.get("file") ?? undefined;
  const demoUrl = import.meta.env.VITE_DEMO_SPLAT_URL;

  return (
    <div className="immersive">
      <button type="button" className="immersive-back" onClick={() => navigate(-1)}>
        ← Back
      </button>
      {sceneId ? (
        <SplatViewer sceneId={sceneId} splatFile={splatFile} immersive />
      ) : demoUrl ? (
        <SplatViewer sourceUrl={demoUrl} title="Sample scene" immersive />
      ) : (
        <div className="immersive-empty">
          <p className="muted">
            No scene selected. Open an archive from <button type="button" className="link-btn" onClick={() => navigate("/library")}>My archives</button> to view it here.
          </p>
        </div>
      )}
    </div>
  );
}
