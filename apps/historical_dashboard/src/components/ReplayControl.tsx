'use client';
import { useRef, useState, useEffect } from 'react';
import { Play, Pause, RotateCcw } from 'lucide-react';
import ChartComponent from './ChartComponent';

type ReplayPoint = {
    time: string;
    open: number;
    high: number;
    low: number;
    close: number;
    delta?: number;
};

export default function ReplayControl() {
    const [symbol, setSymbol] = useState('NSE:NIFTY24DEC25000CE');
    const [speed, setSpeed] = useState(1);
    const [isPlaying, setIsPlaying] = useState(false);
    const [status, setStatus] = useState('Ready');
    const [dataPoints, setDataPoints] = useState<ReplayPoint[]>([]);
    const [availableSymbols, setAvailableSymbols] = useState<string[]>([]);

    const wsRef = useRef<WebSocket | null>(null);

    useEffect(() => {
        const fetchSymbols = async () => {
            try {
                const res = await fetch('http://localhost:8080/available-symbols');
                const data = await res.json();
                if (data.status === 'success') {
                    setAvailableSymbols(data.symbols);
                }
            } catch (err) {
                console.error("Failed to fetch symbols", err);
            }
        };
        fetchSymbols();
    }, []);

    const startReplay = () => {
        // Reset state
        setDataPoints([]);
        setIsPlaying(true);
        setStatus('Connecting to Engine...');

        const ws = new WebSocket('ws://localhost:8765');
        wsRef.current = ws;

        ws.onopen = () => {
            setStatus('Streaming Started');
            ws.send(JSON.stringify({ symbol, speed }));
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.status === 'completed') {
                setStatus('Replay Completed');
                setIsPlaying(false);
                ws.close();
            } else if (data.error) {
                setStatus(`Error: ${data.error}`);
                setIsPlaying(false);
            } else {
                // Accumulate points for the chart
                setDataPoints((prev: ReplayPoint[]) => [...prev, data as ReplayPoint]);
            }
        };

        ws.onerror = () => {
            setStatus('WebSocket Error. Is engine running?');
            setIsPlaying(false);
        };

        ws.onclose = () => {
            setIsPlaying(false);
            if (status === 'Streaming Started') setStatus('Disconnected');
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
        setStatus('Ready');
    }

    return (
        <div className="flex flex-col gap-6 w-full">
            <div className="bg-white/5 backdrop-blur-lg border border-white/10 p-6 rounded-2xl shadow-xl w-full">
                <h2 className="text-2xl font-semibold mb-6 text-white tracking-tight">Replay Engine</h2>

                <div className="flex items-end gap-4 mb-8">
                    <div className="flex flex-col gap-1 flex-1">
                        <label className="text-xs text-zinc-400 uppercase tracking-wider font-semibold">Symbol to Replay</label>
                        <input
                            value={symbol}
                            onChange={e => setSymbol(e.target.value)}
                            disabled={isPlaying}
                            list="available-symbols"
                            placeholder="Type to search database..."
                            className="bg-zinc-900 border border-zinc-700 text-sm text-zinc-200 rounded-lg px-3 py-2.5 focus:ring-2 focus:ring-emerald-500 focus:outline-none transition-all disabled:opacity-50"
                        />
                        <datalist id="available-symbols">
                            {availableSymbols.map(s => <option key={s} value={s} />)}
                        </datalist>
                    </div>

                    <div className="flex flex-col gap-1 w-32">
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
                </div>

                <div className="flex items-center justify-between px-4 py-3 bg-zinc-900/50 rounded-xl border border-zinc-800">
                    <div className="flex items-center gap-3">
                        <div className={`w-2.5 h-2.5 rounded-full ${isPlaying ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'}`}></div>
                        <span className="text-sm font-medium text-zinc-300">Status: <span className="text-zinc-400">{status}</span></span>
                    </div>
                    <span className="text-sm font-medium text-zinc-300">Candles Loaded: <span className="text-emerald-400 bg-emerald-400/10 px-2 py-0.5 rounded ml-1">{dataPoints.length}</span></span>
                </div>
            </div>

            {/* Chart View */}
            <div className="bg-white/5 backdrop-blur-lg border border-white/10 p-6 rounded-2xl shadow-xl w-full h-[calc(100vh-320px)] min-h-[500px]">
                <ChartComponent data={dataPoints} />
            </div>
        </div>
    );
}
