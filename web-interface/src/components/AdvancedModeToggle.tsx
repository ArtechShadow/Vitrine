import { useAppMode } from "../context/AppModeContext";

export default function AdvancedModeToggle() {
  const { advancedMode, setAdvancedMode } = useAppMode();

  return (
    <div className="mode-control">
      <span className="mode-control-label">Mode</span>
      <div className="mode-toggle" role="group" aria-label="Interface mode">
        <button
          type="button"
          className={`mode-toggle-btn ${!advancedMode ? "active" : ""}`}
          onClick={() => setAdvancedMode(false)}
          aria-pressed={!advancedMode}
          title="Simple mode hides technical details"
        >
          Simple
        </button>
        <button
          type="button"
          className={`mode-toggle-btn ${advancedMode ? "active" : ""}`}
          onClick={() => setAdvancedMode(true)}
          aria-pressed={advancedMode}
          title="Advanced mode adds backend details below the main workflow"
        >
          Advanced
        </button>
      </div>
    </div>
  );
}
