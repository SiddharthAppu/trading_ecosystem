'use client';

import { useEffect, useRef } from 'react';
import {
    createChart,
    ColorType,
    IChartApi,
    ISeriesApi,
    CandlestickData,
    LineData,
    UTCTimestamp,
    CandlestickSeries,
    LineSeries
} from 'lightweight-charts';

type ReplayPoint = {
    time: string;
    symbol?: string;
    open?: number | string;
    high?: number | string;
    low?: number | string;
    close?: number | string;
    price?: number | string;
    volume?: number | string;
    bid?: number | string;
    ask?: number | string;
    delta?: number | string;
    implied_volatility?: number | string;
};

export default function ChartComponent({ data }: { data: ReplayPoint[] }) {
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const candlestickSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
    const priceSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
    const deltaSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

    // Determine data type from first data point
    const getDataType = (dataPoints: ReplayPoint[]) => {
        if (!dataPoints || dataPoints.length === 0) return 'unknown';
        const first = dataPoints[0];
        if (first.open !== undefined && first.high !== undefined && first.low !== undefined && first.close !== undefined) {
            // Has OHLC - could be ohlcv_1m or options_ohlc
            return first.delta !== undefined ? 'options_ohlc' : 'ohlcv_1m';
        } else if (first.price !== undefined) {
            return 'market_ticks';
        }
        return 'unknown';
    };

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

        // Add candlestick series for OHLC data
        const candlestickSeries = chart.addSeries(CandlestickSeries, {
            upColor: '#26a69a',
            downColor: '#ef5350',
            borderVisible: false,
            wickUpColor: '#26a69a',
            wickDownColor: '#ef5350',
        });

        // Add price line series for market_ticks or general price tracking
        const priceSeries = chart.addSeries(LineSeries, {
            color: '#f59e0b',
            lineWidth: 2,
            priceScaleId: 'price-axis',
        });

        // Add delta/IV line series
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
        priceSeriesRef.current = priceSeries;
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
        if (!candlestickSeriesRef.current || !priceSeriesRef.current || !deltaSeriesRef.current || !data || data.length === 0) return;

        const dataType = getDataType(data);
        const seenTimes = new Set();
        const formattedCandles: CandlestickData[] = [];
        const formattedPrices: LineData[] = [];
        const formattedDelta: LineData[] = [];

        // Sort data by time
        const sortedData = [...data].sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());

        sortedData.forEach(d => {
            const unixTime = Math.floor(new Date(d.time).getTime() / 1000);
            const chartTime = unixTime as UTCTimestamp;

            if (!isNaN(unixTime) && !seenTimes.has(unixTime)) {
                seenTimes.add(unixTime);

                // Handle different data types
                if (dataType === 'market_ticks') {
                    // For market ticks, show price as a line chart
                    if (d.price !== undefined) {
                        formattedPrices.push({
                            time: chartTime,
                            value: Number(d.price),
                        });
                    }
                    // Optionally show bid/ask as additional series or info
                } else if (dataType === 'ohlcv_1m' || dataType === 'options_ohlc') {
                    // For OHLC data, show candlestick
                    if (d.open !== undefined && d.high !== undefined && d.low !== undefined && d.close !== undefined) {
                        formattedCandles.push({
                            time: chartTime,
                            open: Number(d.open),
                            high: Number(d.high),
                            low: Number(d.low),
                            close: Number(d.close),
                        });
                    }
                    // Show delta or IV in secondary axis
                    const deltaValue = d.delta || d.implied_volatility;
                    if (deltaValue !== undefined) {
                        formattedDelta.push({
                            time: chartTime,
                            value: Number(deltaValue),
                        });
                    }
                }
            }
        });

        // Update chart based on data type
        if (dataType === 'market_ticks' && formattedPrices.length > 0) {
            priceSeriesRef.current.setData(formattedPrices);
            chartRef.current?.timeScale().fitContent();
        } else if ((dataType === 'ohlcv_1m' || dataType === 'options_ohlc') && formattedCandles.length > 0) {
            candlestickSeriesRef.current.setData(formattedCandles);
            if (formattedDelta.length > 0) {
                deltaSeriesRef.current.setData(formattedDelta);
            }
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
