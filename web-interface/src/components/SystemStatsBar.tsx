import { type SystemStats } from "../api/client";

interface Props {
  stats: SystemStats | null;
  loading?: boolean;
}

function StatMeter({
  label,
  value,
  detail,
  percent,
  accent = false,
}: {
  label: string;
  value: string;
  detail?: string;
  percent?: number;
  accent?: boolean;
}) {
  const fill = percent != null ? Math.min(100, Math.max(0, percent)) : null;
  return (
    <div className={`system-stat ${accent ? "accent" : ""}`}>
      <div className="system-stat-head">
        <span className="system-stat-label">{label}</span>
        <span className="system-stat-value">{value}</span>
      </div>
      {fill != null && (
        <div className="system-stat-track">
          <div className="system-stat-fill" style={{ width: `${fill}%` }} />
        </div>
      )}
      {detail && <span className="system-stat-detail muted">{detail}</span>}
    </div>
  );
}

function formatVram(usedMb: number, totalMb: number) {
  if (totalMb >= 1024) {
    return `${(usedMb / 1024).toFixed(1)} / ${(totalMb / 1024).toFixed(0)} GB`;
  }
  return `${Math.round(usedMb)} / ${Math.round(totalMb)} MB`;
}

export default function SystemStatsBar({ stats, loading }: Props) {
  if (!stats && loading) {
    return (
      <div className="system-stats card">
        <p className="muted text-sm">Reading system sensors…</p>
      </div>
    );
  }
  if (!stats) return null;

  const powerDetail =
    stats.gpu_power_w != null
      ? `GPU ${stats.gpu_power_w.toFixed(0)} W + CPU ~${stats.cpu_power_est_w.toFixed(0)} W`
      : `CPU ~${stats.cpu_power_est_w.toFixed(0)} W est.`;

  return (
    <div className="system-stats card">
      <div className="system-stats-head">
        <span className="footer-label">System load</span>
        {stats.gpu_name && <span className="muted text-sm">{stats.gpu_name}</span>}
      </div>
      <div className="system-stats-grid">
        <StatMeter
          label="CPU"
          value={`${stats.cpu_percent.toFixed(0)}%`}
          percent={stats.cpu_percent}
        />
        <StatMeter
          label="RAM"
          value={`${stats.ram_percent.toFixed(0)}%`}
          detail={`${stats.ram_used_gb} / ${stats.ram_total_gb} GB`}
          percent={stats.ram_percent}
        />
        <StatMeter
          label="GPU"
          value={stats.gpu_available ? `${stats.gpu_percent.toFixed(0)}%` : "N/A"}
          percent={stats.gpu_available ? stats.gpu_percent : undefined}
        />
        <StatMeter
          label="VRAM"
          value={stats.gpu_available ? `${stats.vram_percent.toFixed(0)}%` : "N/A"}
          detail={
            stats.gpu_available
              ? formatVram(stats.vram_used_mb, stats.vram_total_mb)
              : "No NVIDIA GPU detected"
          }
          percent={stats.gpu_available ? stats.vram_percent : undefined}
        />
        <StatMeter
          label="Total power"
          value={`${stats.total_power_w.toFixed(0)} W`}
          detail={powerDetail}
          accent
        />
      </div>
    </div>
  );
}