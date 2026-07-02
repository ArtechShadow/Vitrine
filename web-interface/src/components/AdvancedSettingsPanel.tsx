import { useEffect, useState } from "react";
import { getAdvancedBackendOptions, type AdvancedBackendOptions } from "../api/archiveService";
import { useAppMode } from "../context/AppModeContext";
import { DEFAULT_QA_PRESET, QA_PRESETS } from "../lib/qaPresets";
import { SPLAT_PRESETS } from "../lib/splatPresets";

interface AdvancedSettingsPanelProps {
  sceneId?: string;
  scenePath?: string;
  jobId?: string;
}

export default function AdvancedSettingsPanel({
  sceneId,
  scenePath,
  jobId,
}: AdvancedSettingsPanelProps) {
  const { advancedMode } = useAppMode();
  const [options, setOptions] = useState<AdvancedBackendOptions | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!advancedMode) return;
    getAdvancedBackendOptions()
      .then(setOptions)
      .catch((e) => setError(e.message));
  }, [advancedMode]);

  if (!advancedMode) return null;

  return (
    <details className="advanced-panel card">
      <summary>Technical details</summary>
      <div className="advanced-panel-body">
        {error && <p className="error-text">{error}</p>}
        {options && (
          <dl className="advanced-dl">
            <dt>Reconstruction backend</dt>
            <dd>{options.reconstructionBackend}</dd>
            <dt>Scene builder</dt>
            <dd>{options.splatEngine}</dd>
            <dt>Solid model engine</dt>
            <dd>{options.meshEngine}</dd>
            <dt>Find objects engine</dt>
            <dd>{options.objectEngine}</dd>
            <dt>Game engine export</dt>
            <dd>{options.unrealExportAvailable ? "Available" : "Not connected"}</dd>
            <dt>DreamLab backend</dt>
            <dd>{options.dreamLabConnected ? "Connected" : "Local only"}</dd>
          </dl>
        )}

        <h4>Frame extraction</h4>
        <p className="muted">Default preset: {DEFAULT_QA_PRESET.label} @ {DEFAULT_QA_PRESET.fps} FPS</p>
        <ul className="advanced-list muted">
          {QA_PRESETS.map((p) => (
            <li key={p.id}>
              {p.label} — blur {p.blurThreshold}, duplicate {p.duplicateThreshold}
            </li>
          ))}
        </ul>

        <h4>Scene builder presets</h4>
        <ul className="advanced-list muted">
          {SPLAT_PRESETS.map((p) => (
            <li key={p.id}>{p.label} — {p.fallbackIterations} iterations</li>
          ))}
        </ul>

        <h4>Repair / salvage</h4>
        <p className="muted">
          Multi-FPS camera tracking retries, experimental deblur, robust salvage preset.
        </p>

        {(sceneId || scenePath || jobId) && (
          <>
            <h4>Debug</h4>
            <dl className="advanced-dl mono">
              {sceneId && (
                <>
                  <dt>Scene ID</dt>
                  <dd>{sceneId}</dd>
                </>
              )}
              {jobId && (
                <>
                  <dt>Archive task ID</dt>
                  <dd>{jobId}</dd>
                </>
              )}
              {scenePath && (
                <>
                  <dt>Local path</dt>
                  <dd>{scenePath}</dd>
                </>
              )}
            </dl>
          </>
        )}
      </div>
    </details>
  );
}
