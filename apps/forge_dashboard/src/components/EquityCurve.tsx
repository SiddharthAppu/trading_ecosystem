/* ── Equity curve line chart ── */

"use client";

import { useEffect, useRef } from "react";
import { createChart, AreaSeries, type IChartApi, type Time } from "lightweight-charts";
import type { EquityPoint } from "@/lib/types";

interface EquityCurveProps {
  data: EquityPoint[];
  height?: number;
}

export default function EquityCurve({ data, height = 250 }: EquityCurveProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { color: "#1a1a2e" },
        textColor: "#e5e7eb",
      },
      grid: {
        vertLines: { color: "#2a2a3e" },
        horzLines: { color: "#2a2a3e" },
      },
      rightPriceScale: { borderColor: "#3a3a4e" },
      timeScale: { borderColor: "#3a3a4e", timeVisible: true },
    });

    const series = chart.addSeries(AreaSeries, {
      lineColor: "#3b82f6",
      topColor: "rgba(59,130,246,0.3)",
      bottomColor: "rgba(59,130,246,0.02)",
      lineWidth: 2,
    });

    if (data.length > 0) {
      const formatted = data.map((d) => ({
        time: (new Date(d.timestamp).getTime() / 1000) as Time,
        value: d.equity,
      }));
      series.setData(formatted);
      chart.timeScale().fitContent();
    }

    chartRef.current = chart;

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [data, height]);

  return (
    <div className="w-full">
      <h3 className="text-sm font-medium text-gray-400 mb-2">Equity Curve</h3>
      <div
        ref={containerRef}
        className="w-full rounded-lg overflow-hidden border border-gray-800"
      />
    </div>
  );
}
