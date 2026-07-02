import { useEffect, useMemo, useRef, useState } from "react";
import { derivativeUrl, formatStatus, type ColmapReport, type ProgressInfo } from "../api/client";

interface AlignmentFrame {
  index: number;
  name: string;
  registered: boolean;
  position: [number, number, number] | null;
}

interface AlignmentData {
  total_frames: number;
  registered_count: number;
  registration_ratio: number;
  frames: AlignmentFrame[];
}

interface Props {
  sceneId: string;
  cacheBust?: string;
  progress?: ProgressInfo | null;
  colmap?: ColmapReport | null;
  status?: string;
}

const STAGES = [
  { id: "feature_extractor", label: "Find features" },
  { id: "feature_matching", label: "Match photos" },
  { id: "mapper", label: "Solve cameras" },
  { id: "export", label: "Export alignment" },
];

function stageState(stage: string | undefined, id: string): "done" | "active" | "pending" {
  const activeIndex = STAGES.findIndex((entry) => entry.id === stage);
  const itemIndex = STAGES.findIndex((entry) => entry.id === id);
  if (activeIndex < 0) return "pending";
  if (itemIndex < activeIndex) return "done";
  if (itemIndex === activeIndex) return "active";
  return "pending";
}

function AlignmentPath({ frames }: { frames: AlignmentFrame[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const registered = useMemo(
    () => frames.filter((frame) => frame.registered && frame.position),
    [frames],
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const rect = canvas.getBoundingClientRect();
    const width = Math.max(1, Math.floor(rect.width));
    const height = Math.max(1, Math.floor(rect.height));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--surface-2") || "#111";
    ctx.fillRect(0, 0, width, height);

    if (registered.length < 2) return;
    const xs = registered.map((frame) => frame.position![0]);
    const zs = registered.map((frame) => frame.position![2]);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minZ = Math.min(...zs);
    const maxZ = Math.max(...zs);
    const spanX = Math.max(0.001, maxX - minX);
    const spanZ = Math.max(0.001, maxZ - minZ);
    const pad = 22;
    const project = (frame: AlignmentFrame) => ({
      x: pad + ((frame.position![0] - minX) / spanX) * (width - pad * 2),
      y: height - pad - ((frame.position![2] - minZ) / spanZ) * (height - pad * 2),
    });

    ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue("--accent-bright") || "#ff766f";
    ctx.lineWidth = 2;
    ctx.beginPath();
    registered.forEach((frame, index) => {
      const p = project(frame);
      if (index === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    });
    ctx.stroke();

    registered.forEach((frame, index) => {
      const p = project(frame);
      ctx.fillStyle = index === registered.length - 1
        ? getComputedStyle(document.documentElement).getPropertyValue("--contrast-bright") || "#9ff3e9"
        : getComputedStyle(document.documentElement).getPropertyValue("--text") || "#fff";
      ctx.beginPath();
      ctx.arc(p.x, p.y, index % 5 === 0 ? 3.5 : 2.5, 0, Math.PI * 2);
      ctx.fill();
    });
  }, [registered]);

  return <canvas ref={canvasRef} className="alignment-path-canvas" aria-label="Registered camera path" />;
}

export default function AlignmentProcessPanel({ sceneId, cacheBust, progress, colmap, status }: Props) {
  const [data, setData] = useState<AlignmentData | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setMissing(false);
    fetch(derivativeUrl(sceneId, "colmap_alignment.json") + `?t=${encodeURIComponent(cacheBust ?? "")}`)
      .then((response) => {
        if (!response.ok) throw new Error("missing");
        return response.json() as Promise<AlignmentData>;
      })
      .then((payload) => {
        if (!cancelled) setData(payload);
      })
      .catch(() => {
        if (!cancelled) {
          setData(null);
          setMissing(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [sceneId, cacheBust]);

  const total = data?.total_frames ?? colmap?.total_images ?? 0;
  const registered = data?.registered_count ?? colmap?.registered_images ?? 0;
  const ratio = data?.registration_ratio ?? colmap?.registration_ratio ?? (total ? registered / total : 0);

  return (
    <div className="alignment-panel">
      <div className="alignment-summary">
        <div>
          <h3>Photo alignment</h3>
          <p className="muted">
            {progress?.message ?? (status ? formatStatus(status) : "COLMAP camera registration")}
          </p>
        </div>
        <div className="alignment-metrics">
          <span>
            <strong>{registered.toLocaleString()}</strong>
            <small>registered</small>
          </span>
          <span>
            <strong>{total.toLocaleString()}</strong>
            <small>frames</small>
          </span>
          <span>
            <strong>{Math.round(ratio * 100)}%</strong>
            <small>ratio</small>
          </span>
        </div>
      </div>

      <div className="alignment-stage-row">
        {STAGES.map((stage) => (
          <div key={stage.id} className={`alignment-stage alignment-stage--${stageState(progress?.stage, stage.id)}`}>
            <span />
            <strong>{stage.label}</strong>
          </div>
        ))}
      </div>

      {data?.frames?.some((frame) => frame.registered) ? (
        <>
          <AlignmentPath frames={data.frames} />
          <div className="alignment-frame-strip" aria-label="Frame registration strip">
            {data.frames.map((frame) => (
              <span
                key={frame.name}
                className={frame.registered ? "is-registered" : "is-missing"}
                title={`${frame.name}: ${frame.registered ? "registered" : "not registered"}`}
              />
            ))}
          </div>
          <p className="muted text-sm">
            Red path shows solved camera positions. Grey ticks are extracted frames that did not align.
          </p>
        </>
      ) : (
        <div className="alignment-empty">
          <p>{missing ? "Alignment data will appear after COLMAP exports the sparse model." : "Loading alignment data..."}</p>
          <p className="muted text-sm">
            During processing, watch the stages above. After export, this panel shows which photos became solved cameras.
          </p>
        </div>
      )}
    </div>
  );
}
