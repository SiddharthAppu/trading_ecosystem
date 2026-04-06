/* ── Performance metrics cards grid ── */

"use client";

interface MetricCard {
  label: string;
  value: string;
  color?: "green" | "red" | "blue" | "neutral";
}

interface PerformanceMetricsProps {
  metrics: Record<string, number>;
}

function fmt(v: number, decimals = 2): string {
  if (!isFinite(v)) return "—";
  return v.toFixed(decimals);
}

function pnlColor(v: number): "green" | "red" | "neutral" {
  if (v > 0) return "green";
  if (v < 0) return "red";
  return "neutral";
}

const colorClass: Record<string, string> = {
  green: "text-green-400",
  red: "text-red-400",
  blue: "text-blue-400",
  neutral: "text-gray-300",
};

export default function PerformanceMetrics({
  metrics,
}: PerformanceMetricsProps) {
  const cards: MetricCard[] = [
    {
      label: "Total Trades",
      value: String(metrics.total_trades ?? 0),
      color: "blue",
    },
    {
      label: "Win Rate",
      value: `${fmt(metrics.win_rate_pct ?? 0, 1)}%`,
      color: (metrics.win_rate_pct ?? 0) >= 50 ? "green" : "red",
    },
    {
      label: "Net P&L",
      value: `₹${fmt(metrics.net_pnl ?? metrics.total_pnl ?? 0, 0)}`,
      color: pnlColor(metrics.net_pnl ?? metrics.total_pnl ?? 0),
    },
    {
      label: "Return",
      value: `${fmt(metrics.return_pct ?? 0, 2)}%`,
      color: pnlColor(metrics.return_pct ?? 0),
    },
    {
      label: "Sharpe Ratio",
      value: fmt(metrics.sharpe_ratio ?? 0),
      color: (metrics.sharpe_ratio ?? 0) >= 1 ? "green" : "neutral",
    },
    {
      label: "Sortino Ratio",
      value: fmt(metrics.sortino_ratio ?? 0),
      color: (metrics.sortino_ratio ?? 0) >= 1 ? "green" : "neutral",
    },
    {
      label: "Max Drawdown",
      value: `${fmt(metrics.max_drawdown_pct ?? 0, 2)}%`,
      color: "red",
    },
    {
      label: "Profit Factor",
      value: fmt(metrics.profit_factor ?? 0),
      color: (metrics.profit_factor ?? 0) >= 1.5 ? "green" : "neutral",
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {cards.map((card) => (
        <div
          key={card.label}
          className="bg-[#1a1a2e] rounded-lg p-3 border border-gray-800"
        >
          <p className="text-xs text-gray-500 mb-1">{card.label}</p>
          <p className={`text-lg font-semibold ${colorClass[card.color ?? "neutral"]}`}>
            {card.value}
          </p>
        </div>
      ))}
    </div>
  );
}
