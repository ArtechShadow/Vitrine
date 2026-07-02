import { useNavigate, useParams } from "react-router-dom";
import SceneDetail from "./SceneDetail";
import { useAppMode } from "../context/AppModeContext";

/** Wraps the existing technical scene workspace for advanced users and deep editing. */
export default function SceneWorkspace() {
  const { sceneId } = useParams<{ sceneId: string }>();
  const navigate = useNavigate();
  const { advancedMode } = useAppMode();

  if (!sceneId) return null;

  return (
    <div className={`scene-workspace ${advancedMode ? "scene-workspace--advanced" : ""}`}>
      <SceneDetail
        sceneId={sceneId}
        embedded
        onClose={() => navigate(advancedMode ? "/library" : "/")}
        friendlyMode={!advancedMode}
      />
    </div>
  );
}