import { useEffect, useState } from "react";
import { getTools, type ToolStatus } from "../api/client";
import { useAppMode } from "../context/AppModeContext";

export default function BackendStatusPanel() {
  const { advancedMode } = useAppMode();
  const [tools, setTools] = useState<ToolStatus | null>(null);
  const [apiOk, setApiOk] = useState<boolean | null>(null);

  useEffect(() => {
    if (!advancedMode) return;
    getTools()
      .then((t) => {
        setTools(t);
        setApiOk(true);
      })
      .catch(() => {
        setTools(null);
        setApiOk(false);
      });
  }, [advancedMode]);

  if (!advancedMode) return null;

  return (
    <details className="advanced-panel card">
      <summary>API &amp; tools status</summary>
      <div className="advanced-panel-body">
        <p>
          API:{" "}
          <span className={apiOk ? "success-text" : "error-text"}>
            {apiOk === null ? "Checking…" : apiOk ? "Reachable" : "Unreachable"}
          </span>
        </p>
        {tools && (
          <dl className="advanced-dl">
            <dt>FFmpeg</dt>
            <dd>{tools.ffmpeg.available ? tools.ffmpeg.path : "Not found"}</dd>
            <dt>Camera tracking (COLMAP)</dt>
            <dd>{tools.colmap.available ? tools.colmap.path : "Not found"}</dd>
            <dt>Scene builder</dt>
            <dd>
              {tools.splat_training?.available
                ? tools.splat_training.python
                : "Not configured"}
            </dd>
            {tools.gpu_profile && (
              <>
                <dt>GPU profile</dt>
                <dd>
                  {tools.gpu_profile.name} ({tools.gpu_profile.tier})
                </dd>
              </>
            )}
          </dl>
        )}
      </div>
    </details>
  );
}