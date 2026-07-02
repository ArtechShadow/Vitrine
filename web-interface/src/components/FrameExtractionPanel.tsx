import ProcessingPanel from "./ProcessingPanel";
import type { ProgressInfo } from "../api/client";

interface Props {
  sceneId: string;
  progress: ProgressInfo | null;
  running: boolean;
  paused?: boolean;
  onJobControl?: () => void;
}

export default function FrameExtractionPanel({ sceneId, progress, running, paused, onJobControl }: Props) {
  return (
    <div className="extraction-panel extraction-panel-overlay">
      <ProcessingPanel
        title="FFmpeg frame extraction"
        progress={progress}
        running={running}
        paused={paused}
        sceneId={sceneId}
        jobType="extract_frames"
        onJobControl={onJobControl}
        stages={["Prepare video", "Extract frames", "QA analysis", "Contact sheet"]}
      />
      {!progress?.preview && (running || paused) && (
        <p className="muted text-sm extraction-waiting">Waiting for first frame…</p>
      )}
    </div>
  );
}