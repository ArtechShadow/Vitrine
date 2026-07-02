import type { ColmapReport, QaReport } from "../../api/client";
import { useAppMode } from "../../context/AppModeContext";
import { summarizeQuality } from "../../lib/qualitySummary";

interface QualityCheckStepProps {
  qa: QaReport | null;
  colmap: ColmapReport | null;
  loading?: boolean;
}

export default function QualityCheckStep({ qa, colmap, loading }: QualityCheckStepProps) {
  const { advancedMode } = useAppMode();
  const summary = summarizeQuality(qa, colmap);

  if (loading) {
    return (
      <div className="wizard-step-panel">
        <h2>Quality check</h2>
        <p className="muted">Reviewing your capture…</p>
      </div>
    );
  }

  return (
    <div className="wizard-step-panel">
      <h2>Quality check</h2>
      <p className="muted">Here is how your capture looks for creating a 3D archive.</p>

      <div className={`quality-rating quality-rating--${summary.rating}`}>
        <span className="quality-rating-label">{summary.title}</span>
      </div>

      <ul className="quality-advice">
        {summary.advice.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>

      {!summary.canArchive && (
        <p className="error-text">
          This capture may be too sparse to archive. Try adding more angles or a new recording.
        </p>
      )}

      {advancedMode && qa && (
        <details className="advanced-panel card" open>
          <summary>Technical quality details</summary>
          <dl className="advanced-dl">
            <dt>Blur average</dt>
            <dd>{qa.blur?.average?.toFixed(1) ?? "—"}</dd>
            <dt>Blurry frames</dt>
            <dd>{qa.blur?.blurry_frame_count ?? 0}</dd>
            <dt>Sharp frames</dt>
            <dd>{qa.blur?.sharp_frame_count ?? 0}</dd>
            <dt>Frame count</dt>
            <dd>{qa.frame_count}</dd>
            <dt>QA passed</dt>
            <dd>{qa.passed ? "Yes" : "No"}</dd>
          </dl>
        </details>
      )}

      {advancedMode && colmap && (
        <details className="advanced-panel card">
          <summary>Camera tracking diagnostics</summary>
          <dl className="advanced-dl">
            <dt>Registered images</dt>
            <dd>
              {colmap.registered_images} / {colmap.total_images}
            </dd>
            <dt>Registration ratio</dt>
            <dd>{((colmap.registration_ratio ?? 0) * 100).toFixed(0)}%</dd>
            <dt>Point count</dt>
            <dd>{colmap.point_count?.toLocaleString() ?? "—"}</dd>
            <dt>Mean reprojection error</dt>
            <dd>{colmap.mean_reprojection_error?.toFixed(3) ?? "—"}</dd>
          </dl>
        </details>
      )}
    </div>
  );
}