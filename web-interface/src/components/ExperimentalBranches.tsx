import { useEffect, useState } from "react";
import { getBranches, getTools, runArtifixer, runLingbot, runPpisp, type BranchInfo } from "../api/client";

interface Props {
  sceneId: string;
  onRefresh: () => void;
}

export default function ExperimentalBranches({ sceneId, onRefresh }: Props) {
  const [branches, setBranches] = useState<BranchInfo[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getBranches()
      .then(setBranches)
      .catch(() => getTools().then((t) => setBranches(t.branches ?? [])).catch(() => {}));
  }, []);

  async function runBranch(branchId: string, action: () => Promise<void>) {
    setBusy(branchId);
    setError(null);
    try {
      await action();
      onRefresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start branch");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="card">
      <h2>Experimental branches</h2>
      <p className="muted text-sm">
        Optional pipelines; not required for MVP splat training.
      </p>
      {error && <p className="error-text">{error}</p>}
      <div className="branch-list">
        {branches.map((b) => (
          <div key={b.id} className="branch-row">
            <div>
              <strong>{b.name}</strong>
              <span className={`badge ${b.status === "configured" ? "success" : ""}`}>{b.status}</span>
              <p className="muted text-sm branch-purpose">{b.purpose}</p>
            </div>
            {b.id === "lingbot_map" && (
              <button
                type="button"
                onClick={() => runBranch(b.id, () => runLingbot(sceneId))}
                disabled={b.status === "disabled" || busy === b.id}
              >
                {busy === b.id ? "Starting..." : "Run fast preview"}
              </button>
            )}
            {b.id === "ppisp" && (
              <button
                type="button"
                onClick={() => runBranch(b.id, () => runPpisp(sceneId))}
                disabled={b.status === "disabled" || busy === b.id}
              >
                {busy === b.id ? "Starting..." : "Prepare PPiSP"}
              </button>
            )}
            {b.id === "nvidia_artifixer" && (
              <button
                type="button"
                onClick={() => runBranch(b.id, () => runArtifixer(sceneId))}
                disabled={b.status === "disabled" || busy === b.id}
              >
                {busy === b.id ? "Starting..." : "Prepare ArtiFixer"}
              </button>
            )}
            {b.id !== "lingbot_map" && b.id !== "ppisp" && b.id !== "nvidia_artifixer" && (
              <span className="muted text-xs">Phase 8+</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
