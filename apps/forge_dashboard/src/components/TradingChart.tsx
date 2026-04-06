/* ── Trading chart component using lightweight-charts ── */

"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  createSeriesMarkers,
  CandlestickSeries,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type Time,
} from "lightweight-charts";
import type { CandleData, TradeMarker } from "@/lib/types";

interface TradingChartProps {
  candles: CandleData[];
  markers?: TradeMarker[];
  height?: number;
}

export default function TradingChart({
  candles,
  markers = [],
  height = 400,
}: TradingChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  // Create chart once
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
      crosshair: { mode: 0 },
      timeScale: {
        borderColor: "#3a3a4e",
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: { borderColor: "#3a3a4e" },
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderDownColor: "#ef4444",
      borderUpColor: "#22c55e",
      wickDownColor: "#ef4444",
      wickUpColor: "#22c55e",
    });

    const markersPrimitive = createSeriesMarkers(series, []);

    chartRef.current = chart;
    seriesRef.current = series;
    markersRef.current = markersPrimitive;

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
      seriesRef.current = null;
      markersRef.current = null;
    };
  }, [height]);

  // Update data
  useEffect(() => {
    if (!seriesRef.current || candles.length === 0) return;

    const formatted = candles.map((c) => ({
      time: (new Date(c.timestamp).getTime() / 1000) as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));

    seriesRef.current.setData(formatted);

    // Update trade markers
    if (markersRef.current) {
      if (markers.length > 0) {
        const chartMarkers = markers
          .map((m) => ({
            time: (new Date(m.timestamp).getTime() / 1000) as Time,
            position: m.side === "BUY" ? ("belowBar" as const) : ("aboveBar" as const),
            color: m.side === "BUY" ? "#22c55e" : "#ef4444",
            shape: m.side === "BUY" ? ("arrowUp" as const) : ("arrowDown" as const),
            text: m.pnl != null ? `${m.pnl >= 0 ? "+" : ""}${m.pnl.toFixed(0)}` : m.side,
          }))
          .sort((a, b) => (a.time as number) - (b.time as number));
        markersRef.current.setMarkers(chartMarkers);
      } else {
        markersRef.current.setMarkers([]);
      }
    }

    chartRef.current?.timeScale().fitContent();
  }, [candles, markers]);

  return (
    <div
      ref={containerRef}
      className="w-full rounded-lg overflow-hidden border border-gray-800"
    />
  );
}
