'use client';
import { useRef, useState, useEffect } from 'react';
import { Play, Pause, RotateCcw } from 'lucide-react';
import ChartComponent from './ChartComponent';

type ReplayPoint = {
    time: string;
    symbol?: string;
    open?: number;
    high?: number;
    low?: number;
    close?: number;
    price?: number;
    volume?: number;
    bid?: number;
    ask?: number;
    delta?: number;
    implied_volatility?: number;
};

export default function ReplayControl() {
    // Core settings
    const [provider, setProvider] = useState<'' | 'fyers' | 'upstox'>('');
    const [dataType, setDataType] = useState<'' | 'market_ticks' | 'ohlcv_1m' | 'options_ohlc'>('');
    const [symbol, setSymbol] = useState('');
    const [speed, setSpeed] = useState(1);
    
    // Time frame selection
    const [startTime, setStartTime] = useState('');
    const [endTime, setEndTime] = useState('');
    const [useTimeRange, setUseTimeRange] = useState(false);

    // UI state
    const [isPlaying, setIsPlaying] = useState(false);
    const [status, setStatus] = useState('Ready');
    const [dataPoints, setDataPoints] = useState<ReplayPoint[]>([]);
    const [availableSymbols, setAvailableSymbols] = useState<string[]>([]);
    const [recordCount, setRecordCount] = useState(0);
    const [symbolsLoading, setSymbolsLoading] = useState(false);

    const wsRef = useRef<WebSocket | null>(null);

    // Fetch symbols only when both provider and dataType are selected
    useEffect(() => {
        setAvailableSymbols([]);
        setSymbol('');
        if (!provider || !dataType) return;
        const fetchSymbols = async () => {
            setSymbolsLoading(true);
            try {
                const res = await fetch(`http://localhost:8080/available-symbols?provider=${provider}&data_type=${dataType}`);
                const data = await res.json();
                if (data.status === 'success') {
                    setAvailableSymbols(data.symbols);
                }
            } catch (err) {
                console.error("Failed to fetch symbols", err);
            } finally {
                setSymbolsLoading(false);
            }
        };
        fetchSymbols();
    }, [provider, dataType]);

    const startReplay = () => {
        // Reset state
        setDataPoints([]);
        setRecordCount(0);
        setIsPlaying(true);
        setStatus('Connecting to Engine...');

        const ws = new WebSocket('ws://localhost:8765');
        wsRef.current = ws;

        ws.onopen = () => {
            setStatus('Streaming Started');
            const config = {
                symbol,
                provider,
                data_type: dataType,
                speed,
                ...(useTimeRange && startTime && { start_time: startTime }),
                ...(useTimeRange && endTime && { end_time: endTime }),
            };
            ws.send(JSON.stringify(config));
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.status === 'completed') {
                setStatus('Replay Completed');
                setIsPlaying(false);
                ws.close();
            } else if (data.status === 'started') {
                setRecordCount(data.record_count || 0);
                setStatus(`Streaming Started (${data.record_count} records)`);
            } else if (data.status === 'no_data') {
                setStatus(`No data found`);
                setIsPlaying(false);
                ws.close();
            } else if (data.error) {
                setStatus(`Error: ${data.error}`);
                setIsPlaying(false);
            } else if (data.time) {
                // Data point received
                setDataPoints((prev: ReplayPoint[]) => [...prev, data as ReplayPoint]);
            }
        };

        ws.onerror = () => {
            setStatus('WebSocket Error. Is engine running?');
            setIsPlaying(false);
        };

        ws.onclose = () => {
            setIsPlaying(false);
            if (status === 'Streaming Started' || status.includes('records')) setStatus('Disconnected');
        };
    };

    const stopReplay = () => {
        if (wsRef.current) {
            wsRef.current.close();
            setIsPlaying(false);
            setStatus('Paused');
        }
    };

    const resetReplay = () => {
        if (wsRef.current) wsRef.current.close();
        setIsPlaying(false);
        setDataPoints([]);
        setRecordCount(0);
        setStatus('Ready');
    }

    return (
        <div className="flex flex-col gap-6 w-full">
            <div className="bg-white/5 backdrop-blur-lg border border-white/10 p-6 rounded-2xl shadow-xl w-full">
                <h2 className="text-2xl font-semibold mb-6 text-white tracking-tight">Replay Engine</h2>


                {/* First Row: Provider, Data Type, Symbol, Speed */}
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                    {/* Provider first */}
                    <div className="flex flex-col gap-1">
                        <label className="text-xs text-zinc-400 uppercase tracking-wider font-semibold">Provider</label>
                        <select
                            value={provider}
                            onChange={e => {
                                setProvider(e.target.value as 'fyers' | 'upstox');
                                setDataType('');
                                setSymbol('');
                            }}
                            disabled={isPlaying}
                            className="bg-zinc-900 border border-zinc-700 text-sm text-zinc-200 rounded-lg px-3 py-2.5 focus:ring-2 focus:ring-emerald-500 focus:outline-none transition-all disabled:opacity-50">
                            <option value="">Select Provider</option>
                            <option value="fyers">Fyers</option>
                            <option value="upstox">Upstox</option>
                        </select>
                    </div>

                    {/* Data Type second */}
                    <div className="flex flex-col gap-1">
                        <label className="text-xs text-zinc-400 uppercase tracking-wider font-semibold">Data Type</label>
                        <select
                            value={dataType}
                            onChange={e => {
                                setDataType(e.target.value as 'market_ticks' | 'ohlcv_1m' | 'options_ohlc');
                                setSymbol('');
                            }}
                            disabled={isPlaying || !provider}
                            className="bg-zinc-900 border border-zinc-700 text-sm text-zinc-200 rounded-lg px-3 py-2.5 focus:ring-2 focus:ring-emerald-500 focus:outline-none transition-all disabled:opacity-50">
                            <option value="">Select Data Type</option>
                            <option value="market_ticks">Market Ticks</option>
                            <option value="ohlcv_1m">OHLCV 1Min</option>
                            <option value="options_ohlc">Options OHLC</option>
                        </select>
                    </div>

                    {/* Symbol third, only enabled if provider and dataType are set */}
                    <div className="flex flex-col gap-1">
                        <label className="text-xs text-zinc-400 uppercase tracking-wider font-semibold">Symbol</label>
                        <select
                            value={symbol}
                            onChange={e => setSymbol(e.target.value)}
                            disabled={isPlaying || !provider || !dataType || symbolsLoading || availableSymbols.length === 0}
                            className="bg-zinc-900 border border-zinc-700 text-sm text-zinc-200 rounded-lg px-3 py-2.5 focus:ring-2 focus:ring-emerald-500 focus:outline-none transition-all disabled:opacity-50">
                            {!provider || !dataType ? (
                                <option value="">Select provider &amp; data type first</option>
                            ) : symbolsLoading ? (
                                <option value="">Loading symbols...</option>
                            ) : availableSymbols.length === 0 ? (
                                <option value="">No symbols found</option>
                            ) : (
                                <>
                                    <option value="">Select a symbol</option>
                                    {availableSymbols.map(s => <option key={s} value={s}>{s}</option>)}
                                </>
                            )}
                        </select>
                    </div>

                    {/* Speed last */}
                    <div className="flex flex-col gap-1">
                        <label className="text-xs text-zinc-400 uppercase tracking-wider font-semibold">Speed</label>
                        <select
                            value={speed}
                            onChange={e => setSpeed(Number(e.target.value))}
                            disabled={isPlaying}
                            className="bg-zinc-900 border border-zinc-700 text-sm text-zinc-200 rounded-lg px-3 py-2.5 focus:ring-2 focus:ring-emerald-500 focus:outline-none transition-all disabled:opacity-50">
                            <option value={1}>1x</option>
                            <option value={5}>5x</option>
                            <option value={10}>10x</option>
                            <option value={60}>60x (Fast)</option>
                        </select>
                    </div>
                </div>

                {/* Second Row: Time Range Selection */}
                <div className="bg-zinc-900/30 border border-zinc-800 rounded-lg p-4 mb-6">
                    <div className="flex items-center gap-2 mb-3">
                        <input
                            type="checkbox"
                            id="useTimeRange"
                            checked={useTimeRange}
                            onChange={e => setUseTimeRange(e.target.checked)}
                            disabled={isPlaying}
                            className="w-4 h-4 rounded border-zinc-700 text-emerald-600 focus:ring-2 focus:ring-emerald-500 cursor-pointer disabled:opacity-50"
                        />
                        <label htmlFor="useTimeRange" className="text-xs text-zinc-400 uppercase tracking-wider font-semibold cursor-pointer">
                            Filter by Time Range
                        </label>
                    </div>

                    {useTimeRange && (
                        <div className="grid grid-cols-2 gap-3">
                            <div className="flex flex-col gap-1">
                                <label className="text-xs text-zinc-400 uppercase tracking-wider font-semibold">Start Time (ISO)</label>
                                <input
                                    type="datetime-local"
                                    value={startTime}
                                    onChange={e => setStartTime(e.target.value ? new Date(e.target.value).toISOString() : '')}
                                    disabled={isPlaying}
                                    placeholder="2025-01-01T09:15:00"
                                    className="bg-zinc-900 border border-zinc-700 text-sm text-zinc-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-emerald-500 focus:outline-none transition-all disabled:opacity-50"
                                />
                            </div>
                            <div className="flex flex-col gap-1">
                                <label className="text-xs text-zinc-400 uppercase tracking-wider font-semibold">End Time (ISO)</label>
                                <input
                                    type="datetime-local"
                                    value={endTime}
                                    onChange={e => setEndTime(e.target.value ? new Date(e.target.value).toISOString() : '')}
                                    disabled={isPlaying}
                                    placeholder="2025-01-31T15:30:00"
                                    className="bg-zinc-900 border border-zinc-700 text-sm text-zinc-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-emerald-500 focus:outline-none transition-all disabled:opacity-50"
                                />
                            </div>
                        </div>
                    )}
                </div>

                {/* Control Buttons and Status */}
                <div className="flex items-center justify-between gap-4">
                    <div className="flex gap-2">
                        {!isPlaying ? (
                            <button onClick={startReplay} className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-5 py-2.5 rounded-lg font-medium transition-all active:scale-95 shadow-lg shadow-emerald-500/20">
                                <Play size={18} fill="currentColor" /> Play
                            </button>
                        ) : (
                            <button onClick={stopReplay} className="flex items-center gap-2 bg-rose-600 hover:bg-rose-500 text-white px-5 py-2.5 rounded-lg font-medium transition-all active:scale-95 shadow-lg shadow-rose-500/20">
                                <Pause size={18} fill="currentColor" /> Pause
                            </button>
                        )}
                        <button onClick={resetReplay} disabled={isPlaying} className="flex items-center gap-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-4 py-2.5 rounded-lg border border-zinc-700 transition-all active:scale-95 disabled:opacity-50">
                            <RotateCcw size={18} />
                        </button>
                    </div>

                    <div className="flex items-center justify-between gap-6">
                        <div className="flex items-center gap-3">
                            <div className={`w-2.5 h-2.5 rounded-full ${isPlaying ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'}`}></div>
                            <span className="text-sm font-medium text-zinc-300">Status: <span className="text-zinc-400">{status}</span></span>
                        </div>
                        <span className="text-sm font-medium text-zinc-300">Points: <span className="text-emerald-400 bg-emerald-400/10 px-2 py-0.5 rounded ml-1">{dataPoints.length}</span></span>
                    </div>
                </div>
            </div>

            {/* Chart View */}
            <div className="bg-white/5 backdrop-blur-lg border border-white/10 p-6 rounded-2xl shadow-xl w-full h-[calc(100vh-320px)] min-h-[500px]">
                <ChartComponent data={dataPoints} />
            </div>
        </div>
    );
}
