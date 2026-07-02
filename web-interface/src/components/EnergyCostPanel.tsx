import { formatEnergyCost, type EnergySummary, type SystemStats } from "../api/client";

const ELECTRICITY_PENCE_PER_KWH = 24.67;

interface Props {
  stats: SystemStats | null;
  energy?: EnergySummary | null;
  sceneEnergy?: {
    cost_pence: number;
    energy_wh: number;
    rate_pence_per_kwh: number;
  } | null;
  live?: boolean;
  loading?: boolean;
}

function hourlyCostPence(watts: number): number {
  return (watts / 1000) * ELECTRICITY_PENCE_PER_KWH;
}

export default function EnergyCostPanel({
  stats,
  energy,
  sceneEnergy,
  live,
  loading,
}: Props) {
  const totalPence = energy?.cost_pence ?? sceneEnergy?.cost_pence ?? 0;
  const totalWh = energy?.energy_wh ?? sceneEnergy?.energy_wh ?? 0;
  const rate = energy?.rate_pence_per_kwh ?? sceneEnergy?.rate_pence_per_kwh ?? ELECTRICITY_PENCE_PER_KWH;
  const costPerHour = stats ? hourlyCostPence(stats.total_power_w) : null;

  if (loading && live && !stats) {
    return (
      <aside className="energy-cost-panel">
        <span className="footer-label">Cost</span>
        <p className="muted text-sm">Reading…</p>
      </aside>
    );
  }

  if (!live && totalPence <= 0) return null;

  return (
    <aside
      className="energy-cost-panel"
      aria-label={`Electricity cost at ${rate} pence per kilowatt hour`}
    >
      <span className="footer-label">Cost</span>
      {live && costPerHour != null && (
        <p className="energy-cost-line">
          <span className="energy-cost-value">~{formatEnergyCost(costPerHour)}/hr</span>
          <span className="muted energy-cost-meta">{rate}p/kWh</span>
        </p>
      )}
      {totalPence > 0 && (
        <p className="energy-cost-line">
          <span className="energy-cost-label muted">Scene total</span>
          <span className="energy-cost-value">{formatEnergyCost(totalPence)}</span>
          <span className="muted energy-cost-meta">{totalWh.toFixed(2)} Wh</span>
        </p>
      )}
      {live && stats && (
        <p className="muted energy-cost-power">{stats.total_power_w.toFixed(0)} W now</p>
      )}
    </aside>
  );
}