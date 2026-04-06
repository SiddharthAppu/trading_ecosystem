'use client';

import { useEffect, useRef } from 'react';
import {
    createChart,
    ColorType,
    IChartApi,
    ISeriesApi,
    CandlestickData,
    LineData,
    CandlestickSeries,
    LineSeries
} from 'lightweight-charts';

export default function ChartComponent({ data }: { data: any[] }) {
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const candlestickSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
    const deltaSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

    // 1. Initialize the Chart
    useEffect(() => {
        if (!chartContainerRef.current) return;

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: 'transparent' },
                textColor: 'rgba(255, 255, 255, 0.7)',
            },
            grid: {
                vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
                horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
            },
            width: chartContainerRef.current.clientWidth,
            height: chartContainerRef.current.clientHeight || 450,
            timeScale: {
                timeVisible: true,
                secondsVisible: false,
                borderColor: 'rgba(255, 255, 255, 0.1)',
            },
        });

        // Use v5 unified Series API
        const candlestickSeries = chart.addSeries(CandlestickSeries, {
            upColor: '#26a69a',
            downColor: '#ef5350',
            borderVisible: false,
            wickUpColor: '#26a69a',
            wickDownColor: '#ef5350',
        });

        const deltaSeries = chart.addSeries(LineSeries, {
            color: '#6366f1',
            lineWidth: 2,
            priceScaleId: 'delta-axis',
        });

        chart.priceScale('delta-axis').applyOptions({
            scaleMargins: {
                top: 0.1,
                bottom: 0.1,
            },
        });

        chartRef.current = chart;
        candlestickSeriesRef.current = candlestickSeries;
        deltaSeriesRef.current = deltaSeries;

        const handleResize = () => {
            if (chartContainerRef.current && chartRef.current) {
                chartRef.current.applyOptions({
                    width: chartContainerRef.current.clientWidth,
                    height: chartContainerRef.current.clientHeight || 450
                });
            }
        };

        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            chart.remove();
        };
    }, []);

    // 2. Update Data when it changes
    useEffect(() => {
        if (!candlestickSeriesRef.current || !deltaSeriesRef.current || !data || data.length === 0) return;

        const seenTimes = new Set();
        const formattedCandles: CandlestickData[] = [];
        const formattedDelta: LineData[] = [];

        // Sort data by time
        const sortedData = [...data].sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());

        sortedData.forEach(d => {
            const unixTime = Math.floor(new Date(d.time as string).getTime() / 1000);

            if (!isNaN(unixTime) && !seenTimes.has(unixTime)) {
                seenTimes.add(unixTime);
                formattedCandles.push({
                    time: unixTime as any,
                    open: Number(d.open),
                    high: Number(d.high),
                    low: Number(d.low),
                    close: Number(d.close),
                });
                formattedDelta.push({
                    time: unixTime as any,
                    value: Number(d.delta || 0),
                });
            }
        });

        if (formattedCandles.length > 0) {
            candlestickSeriesRef.current.setData(formattedCandles);
            deltaSeriesRef.current.setData(formattedDelta);
            chartRef.current?.timeScale().fitContent();
        }

    }, [data]);

    return (
        <div className="w-full h-full relative bg-zinc-950/20 rounded-xl overflow-hidden" ref={chartContainerRef}>
            {(!data || data.length === 0) && (
                <div className="absolute inset-0 flex items-center justify-center text-zinc-500 flex-col gap-3 z-10 bg-zinc-950/50">
                    <div className="w-16 h-16 border-4 border-zinc-800 border-t-zinc-600 rounded-full animate-spin"></div>
                    <p className="font-medium animate-pulse">Waiting for replay data...</p>
                </div>
            )}
        </div>
    );
}
