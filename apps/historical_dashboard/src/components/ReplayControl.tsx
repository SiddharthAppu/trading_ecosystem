'use client';
import { useRef, useState, useEffect } from 'react';
import { Play, Pause, RotateCcw, ChevronDown, ChevronUp } from 'lucide-react';
import ChartComponent from './ChartComponent';

type DataType = '' | 'market_ticks' | 'ohlcv_1m' | 'ohlcv_1min_from_ticks' | 'options_ohlc';
type Timeframe = '1m' | '5m' | '10m';

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
    ema_20?: number;
    sma_20?: number;
    rsi_14?: number;
    macd_line?: number;
    macd_signal?: number;
    macd_histogram?: number;
};

const INDICATOR_OPTIONS = [
    { key: 'ema_20', label: 'EMA 20' },
    { key: 'sma_20', label: 'SMA 20' },
    { key: 'rsi_14', label: 'RSI 14' },
    { key: 'macd', label: 'MACD' },
] as const;

type IndicatorKey = typeof INDICATOR_OPTIONS[number]['key'];

type PaneState = {
    symbol: string;
    dataType: DataType;
    timeframe: Timeframe;
    selectedIndicators: IndicatorKey[];
    dataPoints: ReplayPoint[];
    availableSymbols: string[];
    symbolsLoading: boolean;
    status: string;
    recordCount: number;
};

type ReplayMode = 'stream' | 'load';
type LogicalRange = { from: number; to: number };

const MAX_PANES = 4;
const REPLAY_LOAD_API = 'http://localhost:8766/replay/load';

function createInitialPane(): PaneState {
    return {
        symbol: '',
        dataType: '',
        timeframe: '1m',
        selectedIndicators: [],
        dataPoints: [],
        availableSymbols: [],
        symbolsLoading: false,
        status: 'Ready',
        recordCount: 0,
    };
}

export default function ReplayControl() {
    // Shared settings
    const [provider, setProvider] = useState<'' | 'fyers' | 'upstox'>('');
    const [speed, setSpeed] = useState(1);
    const [chartPanes, setChartPanes] = useState<1 | 2 | 3 | 4>(1);
    const [activePane, setActivePane] = useState(0);
    const [paneStates, setPaneStates] = useState<PaneState[]>(
        Array.from({ length: MAX_PANES }, () => createInitialPane())
    );
    
    // Time frame selection
    const [startTime, setStartTime] = useState('');
    const [endTime, setEndTime] = useState('');
    const [useTimeRange, setUseTimeRange] = useState(false);
    const [selectedExpiry, setSelectedExpiry] = useState('');
    const [expiryOptions, setExpiryOptions] = useState<string[]>([]);
    const [expiriesLoading, setExpiriesLoading] = useState(false);

    // UI state
    const [isPlaying, setIsPlaying] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [replayMode, setReplayMode] = useState<ReplayMode>('stream');
    const [syncEnabled, setSyncEnabled] = useState(false);
    const [sharedVisibleRange, setSharedVisibleRange] = useState<LogicalRange | null>(null);
    const [sharedHoverTime, setSharedHoverTime] = useState<number | null>(null);
    const [isControlCollapsed, setIsControlCollapsed] = useState(false);

    const wsRefs = useRef<Map<number, WebSocket>>(new Map());
    const liveStreamsRef = useRef(0);

    const visiblePaneIndices = Array.from({ length: chartPanes }, (_, idx) => idx);
    const currentPane = paneStates[activePane] ?? createInitialPane();

    useEffect(() => {
        setActivePane(prev => (prev >= chartPanes ? 0 : prev));
    }, [chartPanes]);

    const updatePaneState = (paneIndex: number, updater: (prev: PaneState) => PaneState) => {
        setPaneStates(prev => prev.map((pane, idx) => (idx === paneIndex ? updater(pane) : pane)));
    };

    const setPaneStatus = (paneIndex: number, status: string) => {
        updatePaneState(paneIndex, prev => ({ ...prev, status }));
    };

    const fetchSymbolsForPane = async (
        paneIndex: number,
        nextProvider: '' | 'fyers' | 'upstox',
        nextDataType: DataType,
        fromTime?: string,
        toTimeValue?: string,
        expiryDate?: string,
    ) => {
        updatePaneState(paneIndex, prev => ({ ...prev, symbolsLoading: true, availableSymbols: [], symbol: '' }));
        if (!nextProvider || !nextDataType) {
            updatePaneState(paneIndex, prev => ({ ...prev, symbolsLoading: false }));
            return;
        }

        try {
            const params = new URLSearchParams({
                provider: nextProvider,
                data_type: nextDataType,
            });
            if (fromTime) {
                params.set('from_time', fromTime);
            }
            if (toTimeValue) {
                params.set('to_time', toTimeValue);
            }
            if (expiryDate) {
                params.set('expiry_date', expiryDate);
            }

            const res = await fetch(`http://localhost:8080/available-symbols?${params.toString()}`);
            const data = await res.json();
            updatePaneState(paneIndex, prev => ({
                ...prev,
                symbolsLoading: false,
                availableSymbols: data.status === 'success' ? data.symbols : [],
            }));
        } catch (err) {
            console.error('Failed to fetch symbols', err);
            updatePaneState(paneIndex, prev => ({ ...prev, symbolsLoading: false, status: 'Failed to load symbols' }));
        }
    };

    const refreshVisiblePaneSymbols = () => {
        visiblePaneIndices.forEach((idx) => {
            const pane = paneStates[idx];
            if (!pane.dataType) {
                return;
            }
            fetchSymbolsForPane(
                idx,
                provider,
                pane.dataType,
                useTimeRange ? startTime : undefined,
                useTimeRange ? endTime : undefined,
                selectedExpiry || undefined,
            );
        });
    };

    const fetchExpiryOptions = async (nextProvider: '' | 'fyers' | 'upstox', dataTypeForExpiry?: DataType) => {
        if (!nextProvider) {
            setExpiryOptions([]);
            setSelectedExpiry('');
            return;
        }

        const chosenDataType = dataTypeForExpiry || paneStates[activePane]?.dataType || 'options_ohlc';
        if (!chosenDataType) {
            setExpiryOptions([]);
            setSelectedExpiry('');
            return;
        }

        setExpiriesLoading(true);
        try {
            const params = new URLSearchParams({
                provider: nextProvider,
                data_type: chosenDataType,
                lookback_days: '30',
            });
            const res = await fetch(`http://localhost:8080/available-expiry-options?${params.toString()}`);
            const data = await res.json();
            if (data.status === 'success') {
                setExpiryOptions(data.expiry_options || []);
            } else {
                setExpiryOptions([]);
            }
        } catch (err) {
            console.error('Failed to fetch expiry options', err);
            setExpiryOptions([]);
        } finally {
            setExpiriesLoading(false);
        }
    };

    const closeAllSockets = () => {
        wsRefs.current.forEach(ws => ws.close());
        wsRefs.current.clear();
        liveStreamsRef.current = 0;
    };

    const markStreamDone = () => {
        liveStreamsRef.current = Math.max(0, liveStreamsRef.current - 1);
        if (liveStreamsRef.current === 0) {
            setIsPlaying(false);
        }
    };

    const startReplay = () => {
        if (!provider) {
            return;
        }

        const configs = visiblePaneIndices.map(idx => ({ idx, pane: paneStates[idx] }));
        const runnable = configs.filter(({ pane }) => pane.symbol && pane.dataType);

        if (runnable.length === 0) {
            visiblePaneIndices.forEach(idx => setPaneStatus(idx, 'Select symbol and data type'));
            return;
        }

        closeAllSockets();

        setPaneStates(prev => prev.map((pane, idx) => (
            idx < chartPanes
                ? {
                    ...pane,
                    dataPoints: [],
                    recordCount: 0,
                    status: runnable.some(item => item.idx === idx) ? 'Connecting...' : 'Missing config',
                }
                : pane
        )));

        setIsPlaying(true);
        liveStreamsRef.current = runnable.length;

        runnable.forEach(({ idx, pane }) => {
            const ws = new WebSocket('ws://localhost:8765');
            wsRefs.current.set(idx, ws);

            ws.onopen = () => {
                setPaneStatus(idx, 'Streaming Started');
                const config = {
                    symbol: pane.symbol,
                    provider,
                    data_type: pane.dataType,
                    timeframe: pane.timeframe,
                    indicators: pane.selectedIndicators,
                    speed,
                    ...(useTimeRange && startTime && { start_time: startTime }),
                    ...(useTimeRange && endTime && { end_time: endTime }),
                };
                ws.send(JSON.stringify(config));
            };

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.status === 'completed') {
                    setPaneStatus(idx, 'Replay Completed');
                    ws.close();
                } else if (data.status === 'started') {
                    updatePaneState(idx, prev => ({
                        ...prev,
                        recordCount: data.record_count || 0,
                        status: `Streaming Started (${data.record_count} records)`,
                    }));
                } else if (data.status === 'no_data') {
                    setPaneStatus(idx, 'No data found');
                    ws.close();
                } else if (data.error) {
                    setPaneStatus(idx, `Error: ${data.error}`);
                    ws.close();
                } else if (data.time) {
                    updatePaneState(idx, prev => ({ ...prev, dataPoints: [...prev.dataPoints, data as ReplayPoint] }));
                }
            };

            ws.onerror = () => {
                setPaneStatus(idx, 'WebSocket Error. Is engine running?');
            };

            ws.onclose = () => {
                if (wsRefs.current.get(idx) === ws) {
                    wsRefs.current.delete(idx);
                    markStreamDone();
                }
            };
        });
    };

    const loadReplay = async () => {
        if (isLoading) {
            return;
        }
        if (!provider) {
            return;
        }

        const configs = visiblePaneIndices.map(idx => ({ idx, pane: paneStates[idx] }));
        const runnable = configs.filter(({ pane }) => pane.symbol && pane.dataType);

        if (runnable.length === 0) {
            visiblePaneIndices.forEach(idx => setPaneStatus(idx, 'Select symbol and data type'));
            return;
        }

        closeAllSockets();
        setIsLoading(true);
        setPaneStates(prev => prev.map((pane, idx) => (
            idx < chartPanes
                ? {
                    ...pane,
                    dataPoints: [],
                    recordCount: 0,
                    status: runnable.some(item => item.idx === idx) ? 'Loading...' : 'Missing config',
                }
                : pane
        )));

        await Promise.all(runnable.map(async ({ idx, pane }) => {
            const params = new URLSearchParams({
                symbol: pane.symbol,
                provider,
                data_type: pane.dataType,
                timeframe: pane.timeframe,
            });

            pane.selectedIndicators.forEach(indicator => params.append('indicators', indicator));
            if (useTimeRange && startTime) {
                params.set('start_time', startTime);
            }
            if (useTimeRange && endTime) {
                params.set('end_time', endTime);
            }

            try {
                const res = await fetch(`${REPLAY_LOAD_API}?${params.toString()}`);
                const data = await res.json();
                if (!res.ok || data.error) {
                    throw new Error(data.error || 'Failed to load replay');
                }

                updatePaneState(idx, prev => ({
                    ...prev,
                    dataPoints: (data.records || []) as ReplayPoint[],
                    recordCount: Number(data.record_count || 0),
                    status: `Loaded (${data.record_count || 0} records)`,
                }));
            } catch (err) {
                const msg = err instanceof Error ? err.message : 'Failed to load replay';
                setPaneStatus(idx, `Error: ${msg}`);
            }
        }));
        setIsLoading(false);
    };

    const stopReplay = () => {
        closeAllSockets();
        setIsPlaying(false);
        setIsLoading(false);
        setPaneStates(prev => prev.map((pane, idx) => (
            idx < chartPanes ? { ...pane, status: 'Paused' } : pane
        )));
    };

    const resetReplay = () => {
        closeAllSockets();
        setIsPlaying(false);
        setIsLoading(false);
        setPaneStates(prev => prev.map((pane, idx) => (
            idx < chartPanes
                ? { ...pane, dataPoints: [], recordCount: 0, status: 'Ready' }
                : pane
        )));
    };

    useEffect(() => {
        return () => {
            closeAllSockets();
        };
    }, []);

    const indicatorsDisabled = isPlaying || currentPane.dataType === 'market_ticks' || !currentPane.dataType;

    const updateActivePane = (updater: (pane: PaneState) => PaneState) => {
        updatePaneState(activePane, updater);
    };

    const toggleIndicator = (key: IndicatorKey) => {
        updateActivePane(prev => ({
            ...prev,
            selectedIndicators: prev.selectedIndicators.includes(key)
                ? prev.selectedIndicators.filter(k => k !== key)
                : [...prev.selectedIndicators, key],
        }));
    };

    // Helper to get short indicator names for header
    const getIndicatorShortNames = () => {
        return currentPane.selectedIndicators
            .map(key => {
                const option = INDICATOR_OPTIONS.find(o => o.key === key);
                return option?.label || '';
            })
            .filter(Boolean)
            .join(', ') || 'None';
    };

    const totalVisiblePoints = visiblePaneIndices.reduce((sum, idx) => sum + paneStates[idx].dataPoints.length, 0);
    const totalVisibleRecords = visiblePaneIndices.reduce((sum, idx) => sum + paneStates[idx].recordCount, 0);

    const handleVisibleRangeChange = (sourcePane: number, range: LogicalRange | null) => {
        if (!syncEnabled || !visiblePaneIndices.includes(sourcePane)) {
            return;
        }
        setSharedVisibleRange(range);
    };

    const handleHoverTimeChange = (sourcePane: number, time: number | null) => {
        if (!syncEnabled || !visiblePaneIndices.includes(sourcePane)) {
            return;
        }
        setSharedHoverTime(time);
    };

    return (
        <div className="flex flex-col gap-4 w-full h-screen">
            {/* Collapsible Control Section */}
            <div className="bg-white/5 backdrop-blur-lg border border-white/10 rounded-2xl shadow-xl w-full overflow-hidden">
                {/* Header */}
                <button
                    onClick={() => setIsControlCollapsed(!isControlCollapsed)}
                    className="w-full px-6 py-4 hover:bg-white/10 transition-colors duration-200"
                >
                    <div className="flex items-center justify-between gap-4">
                        <div className="flex items-center gap-4 flex-1 min-w-0">
                            <span className="text-lg font-semibold text-white whitespace-nowrap">Replay Engine</span>
                            {isControlCollapsed && (
                                <div className="flex items-center gap-6 text-sm text-zinc-400 overflow-x-auto">
                                    {provider && <span><span className="text-zinc-500">Provider:</span> <span className="text-zinc-300">{provider}</span></span>}
                                    {currentPane.symbol && <span><span className="text-zinc-500">Symbol:</span> <span className="text-zinc-300">{currentPane.symbol}</span></span>}
                                    {currentPane.dataType && <span><span className="text-zinc-500">Type:</span> <span className="text-zinc-300">{currentPane.dataType.replace(/_/g, ' ')}</span></span>}
                                    {(currentPane.dataType !== 'market_ticks' && currentPane.dataType !== 'options_ohlc') && <span><span className="text-zinc-500">TF:</span> <span className="text-zinc-300">{currentPane.timeframe}</span></span>}
                                    {currentPane.selectedIndicators.length > 0 && <span><span className="text-zinc-500">Indicators:</span> <span className="text-zinc-300">{getIndicatorShortNames()}</span></span>}
                                    {speed !== 1 && <span><span className="text-zinc-500">Speed:</span> <span className="text-zinc-300">{speed}x</span></span>}
                                    <span><span className="text-zinc-500">Active Pane:</span> <span className="text-zinc-300">{activePane + 1}</span></span>
                                    <span><span className="text-zinc-500">Charts:</span> <span className="text-zinc-300">{chartPanes}</span></span>
                                </div>
                            )}
                        </div>
                        {isControlCollapsed ? (
                            <ChevronDown size={20} className="text-zinc-400 flex-shrink-0" />
                        ) : (
                            <ChevronUp size={20} className="text-zinc-400 flex-shrink-0" />
                        )}
                    </div>
                </button>

                {/* Expandable Content */}
                <div className={`overflow-hidden transition-all duration-300 ${isControlCollapsed ? 'max-h-0' : 'max-h-[1000px]'}`}>
                    <div className="px-6 py-6 border-t border-white/10 space-y-6">


                {/* First Row: Provider, Active Pane, Data Type, Symbol, Timeframe, Chart Panes */}
                <div className="grid grid-cols-1 md:grid-cols-6 gap-4 mb-6">
                    {/* Provider first */}
                    <div className="flex flex-col gap-1">
                        <label className="text-xs text-zinc-400 uppercase tracking-wider font-semibold">Provider</label>
                        <select
                            value={provider}
                            onChange={e => {
                                const nextProvider = e.target.value as 'fyers' | 'upstox' | '';
                                setProvider(nextProvider);
                                setPaneStates(prev => prev.map(pane => ({
                                    ...pane,
                                    symbol: '',
                                    availableSymbols: [],
                                    status: 'Ready',
                                })));
                                paneStates.forEach((pane, idx) => {
                                    if (pane.dataType) {
                                        fetchSymbolsForPane(
                                            idx,
                                            nextProvider,
                                            pane.dataType,
                                            useTimeRange ? startTime : undefined,
                                            useTimeRange ? endTime : undefined,
                                            selectedExpiry || undefined,
                                        );
                                    }
                                });
                                fetchExpiryOptions(nextProvider);
                            }}
                            disabled={isPlaying || isLoading}
                            className="bg-zinc-900 border border-zinc-700 text-sm text-zinc-200 rounded-lg px-3 py-2.5 focus:ring-2 focus:ring-emerald-500 focus:outline-none transition-all disabled:opacity-50">
                            <option value="">Select Provider</option>
                            <option value="fyers">Fyers</option>
                            <option value="upstox">Upstox</option>
                        </select>
                    </div>

                    <div className="flex flex-col gap-1">
                        <label className="text-xs text-zinc-400 uppercase tracking-wider font-semibold">Active Pane</label>
                        <select
                            value={activePane}
                            onChange={e => setActivePane(Number(e.target.value))}
                            className="bg-zinc-900 border border-zinc-700 text-sm text-zinc-200 rounded-lg px-3 py-2.5 focus:ring-2 focus:ring-emerald-500 focus:outline-none transition-all"
                        >
                            {visiblePaneIndices.map(idx => (
                                <option key={idx} value={idx}>Pane {idx + 1}</option>
                            ))}
                        </select>
                    </div>

                    {/* Data Type second */}
                    <div className="flex flex-col gap-1">
                        <label className="text-xs text-zinc-400 uppercase tracking-wider font-semibold">Data Type</label>
                        <select
                            value={currentPane.dataType}
                            onChange={e => {
                                const nextDataType = e.target.value as DataType;
                                updateActivePane(prev => ({
                                    ...prev,
                                    dataType: nextDataType,
                                    symbol: '',
                                    selectedIndicators: [],
                                    availableSymbols: [],
                                }));
                                fetchSymbolsForPane(
                                    activePane,
                                    provider,
                                    nextDataType,
                                    useTimeRange ? startTime : undefined,
                                    useTimeRange ? endTime : undefined,
                                    selectedExpiry || undefined,
                                );
                                fetchExpiryOptions(provider, nextDataType);
                            }}
                            disabled={isPlaying || isLoading || !provider}
                            className="bg-zinc-900 border border-zinc-700 text-sm text-zinc-200 rounded-lg px-3 py-2.5 focus:ring-2 focus:ring-emerald-500 focus:outline-none transition-all disabled:opacity-50">
                            <option value="">Select Data Type</option>
                            <option value="market_ticks">Market Ticks</option>
                            <option value="ohlcv_1m">OHLCV 1Min</option>
                            <option value="ohlcv_1min_from_ticks">OHLCV 1Min (From Ticks)</option>
                            <option value="options_ohlc">Options OHLC</option>
                        </select>
                    </div>

                    {/* Symbol third, only enabled if provider and dataType are set */}
                    <div className="flex flex-col gap-1">
                        <label className="text-xs text-zinc-400 uppercase tracking-wider font-semibold">Symbol</label>
                        <select
                            value={currentPane.symbol}
                            onChange={e => updateActivePane(prev => ({ ...prev, symbol: e.target.value }))}
                            disabled={isPlaying || isLoading || !provider || !currentPane.dataType || currentPane.symbolsLoading || currentPane.availableSymbols.length === 0}
                            className="bg-zinc-900 border border-zinc-700 text-sm text-zinc-200 rounded-lg px-3 py-2.5 focus:ring-2 focus:ring-emerald-500 focus:outline-none transition-all disabled:opacity-50">
                            {!provider || !currentPane.dataType ? (
                                <option value="">Select provider &amp; data type first</option>
                            ) : currentPane.symbolsLoading ? (
                                <option value="">Loading symbols...</option>
                            ) : currentPane.availableSymbols.length === 0 ? (
                                <option value="">No symbols found</option>
                            ) : (
                                <>
                                    <option value="">Select a symbol</option>
                                    {currentPane.availableSymbols.map(s => <option key={s} value={s}>{s}</option>)}
                                </>
                            )}
                        </select>
                    </div>

                    <div className="flex flex-col gap-1">
                        <label className="text-xs text-zinc-400 uppercase tracking-wider font-semibold">Timeframe</label>
                        <select
                            value={currentPane.timeframe}
                            onChange={e => updateActivePane(prev => ({ ...prev, timeframe: e.target.value as Timeframe }))}
                            disabled={isPlaying || isLoading || currentPane.dataType === 'market_ticks' || currentPane.dataType === 'options_ohlc'}
                            className="bg-zinc-900 border border-zinc-700 text-sm text-zinc-200 rounded-lg px-3 py-2.5 focus:ring-2 focus:ring-emerald-500 focus:outline-none transition-all disabled:opacity-50">
                            <option value="1m">1m</option>
                            <option value="5m">5m</option>
                            <option value="10m">10m</option>
                        </select>
                    </div>

                    <div className="flex flex-col gap-1">
                        <label className="text-xs text-zinc-400 uppercase tracking-wider font-semibold">Chart Panes</label>
                        <select
                            value={chartPanes}
                            onChange={e => setChartPanes(Number(e.target.value) as 1 | 2 | 3 | 4)}
                            className="bg-zinc-900 border border-zinc-700 text-sm text-zinc-200 rounded-lg px-3 py-2.5 focus:ring-2 focus:ring-emerald-500 focus:outline-none transition-all"
                        >
                            <option value={1}>1</option>
                            <option value={2}>2</option>
                            <option value={3}>3</option>
                            <option value={4}>4</option>
                        </select>
                    </div>

                    <div className="flex flex-col gap-1">
                        <label className="text-xs text-zinc-400 uppercase tracking-wider font-semibold">Speed</label>
                        <select
                            value={speed}
                            onChange={e => setSpeed(Number(e.target.value))}
                            disabled={isPlaying || isLoading || replayMode === 'load'}
                            className="bg-zinc-900 border border-zinc-700 text-sm text-zinc-200 rounded-lg px-3 py-2.5 focus:ring-2 focus:ring-emerald-500 focus:outline-none transition-all disabled:opacity-50">
                            <option value={1}>1x</option>
                            <option value={5}>5x</option>
                            <option value={10}>10x</option>
                            <option value={60}>60x (Fast)</option>
                        </select>
                    </div>
                </div>

                {/* First Option: Time Range + Expiry Assisted Filtering */}
                <div className="bg-zinc-900/30 border border-zinc-800 rounded-lg p-4 mb-6">
                    <div className="text-xs text-zinc-400 uppercase tracking-wider font-semibold mb-3">Filter by Time Range</div>
                    <div className="flex items-center gap-2 mb-3">
                        <input
                            type="checkbox"
                            id="useTimeRange"
                            checked={useTimeRange}
                            onChange={e => {
                                const checked = e.target.checked;
                                setUseTimeRange(checked);
                                if (!checked) {
                                    setStartTime('');
                                    setEndTime('');
                                }
                                setTimeout(refreshVisiblePaneSymbols, 0);
                            }}
                            disabled={isPlaying || isLoading}
                            className="w-4 h-4 rounded border-zinc-700 text-emerald-600 focus:ring-2 focus:ring-emerald-500 cursor-pointer disabled:opacity-50"
                        />
                        <label htmlFor="useTimeRange" className="text-xs text-zinc-400 uppercase tracking-wider font-semibold cursor-pointer">
                            Enable date range symbol filtering
                        </label>
                    </div>

                    {useTimeRange && (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
                            <div className="flex flex-col gap-1">
                                <label className="text-xs text-zinc-400 uppercase tracking-wider font-semibold">Start Time (ISO)</label>
                                <input
                                    type="datetime-local"
                                    value={startTime}
                                    onChange={e => {
                                        const value = e.target.value ? new Date(e.target.value).toISOString() : '';
                                        setStartTime(value);
                                        setTimeout(refreshVisiblePaneSymbols, 0);
                                    }}
                                    disabled={isPlaying || isLoading}
                                    placeholder="2025-01-01T09:15:00"
                                    className="bg-zinc-900 border border-zinc-700 text-sm text-zinc-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-emerald-500 focus:outline-none transition-all disabled:opacity-50"
                                />
                            </div>
                            <div className="flex flex-col gap-1">
                                <label className="text-xs text-zinc-400 uppercase tracking-wider font-semibold">End Time (ISO)</label>
                                <input
                                    type="datetime-local"
                                    value={endTime}
                                    onChange={e => {
                                        const value = e.target.value ? new Date(e.target.value).toISOString() : '';
                                        setEndTime(value);
                                        setTimeout(refreshVisiblePaneSymbols, 0);
                                    }}
                                    disabled={isPlaying || isLoading}
                                    placeholder="2025-01-31T15:30:00"
                                    className="bg-zinc-900 border border-zinc-700 text-sm text-zinc-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-emerald-500 focus:outline-none transition-all disabled:opacity-50"
                                />
                            </div>
                        </div>
                    )}

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div className="flex flex-col gap-1">
                            <label className="text-xs text-zinc-400 uppercase tracking-wider font-semibold">Expiry Date Token (Past 30 Days)</label>
                            <select
                                value={selectedExpiry}
                                onChange={e => {
                                    setSelectedExpiry(e.target.value);
                                    setTimeout(refreshVisiblePaneSymbols, 0);
                                }}
                                disabled={isPlaying || isLoading || expiriesLoading || !provider}
                                className="bg-zinc-900 border border-zinc-700 text-sm text-zinc-200 rounded-lg px-3 py-2.5 focus:ring-2 focus:ring-emerald-500 focus:outline-none transition-all disabled:opacity-50"
                            >
                                <option value="">All expiries</option>
                                {expiryOptions.map(exp => (
                                    <option key={exp} value={exp}>{exp}</option>
                                ))}
                            </select>
                        </div>
                        <div className="flex items-end">
                            <button
                                type="button"
                                onClick={() => fetchExpiryOptions(provider, currentPane.dataType || 'options_ohlc')}
                                disabled={isPlaying || isLoading || !provider || expiriesLoading}
                                className="bg-zinc-800 hover:bg-zinc-700 text-zinc-200 px-4 py-2.5 rounded-lg border border-zinc-700 transition-all disabled:opacity-50"
                            >
                                {expiriesLoading ? 'Refreshing Expiries...' : 'Refresh Expiry Options'}
                            </button>
                        </div>
                    </div>
                </div>

                <div className="bg-zinc-900/30 border border-zinc-800 rounded-lg p-4 mb-6">
                    <div className="text-xs text-zinc-400 uppercase tracking-wider font-semibold mb-3">Replay Mode</div>
                    <div className="flex gap-2">
                        <button
                            type="button"
                            onClick={() => setReplayMode('stream')}
                            disabled={isPlaying || isLoading}
                            className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-all ${
                                replayMode === 'stream'
                                    ? 'bg-emerald-500/20 border-emerald-500 text-emerald-300'
                                    : 'bg-zinc-900 border-zinc-700 text-zinc-300 hover:border-zinc-500'
                            }`}
                        >
                            Stream
                        </button>
                        <button
                            type="button"
                            onClick={() => setReplayMode('load')}
                            disabled={isPlaying || isLoading}
                            className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-all ${
                                replayMode === 'load'
                                    ? 'bg-cyan-500/20 border-cyan-500 text-cyan-300'
                                    : 'bg-zinc-900 border-zinc-700 text-zinc-300 hover:border-zinc-500'
                            }`}
                        >
                            Load All
                        </button>
                        <button
                            type="button"
                            onClick={() => {
                                setSyncEnabled(prev => !prev);
                                if (syncEnabled) {
                                    setSharedVisibleRange(null);
                                    setSharedHoverTime(null);
                                }
                            }}
                            disabled={isPlaying || isLoading}
                            className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-all ${
                                syncEnabled
                                    ? 'bg-indigo-500/20 border-indigo-500 text-indigo-300'
                                    : 'bg-zinc-900 border-zinc-700 text-zinc-300 hover:border-zinc-500'
                            }`}
                        >
                            Sync {syncEnabled ? 'On' : 'Off'}
                        </button>
                    </div>
                </div>

                <div className="bg-zinc-900/30 border border-zinc-800 rounded-lg p-4 mb-6">
                    <div className="text-xs text-zinc-400 uppercase tracking-wider font-semibold mb-3">Pane Configuration</div>
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
                        {visiblePaneIndices.map(idx => {
                            const pane = paneStates[idx];
                            const active = idx === activePane;
                            return (
                                <button
                                    key={`pane-config-${idx}`}
                                    type="button"
                                    onClick={() => setActivePane(idx)}
                                    className={`text-left p-3 rounded-lg border transition-all ${
                                        active
                                            ? 'border-emerald-500/70 bg-emerald-500/10'
                                            : 'border-zinc-700 bg-zinc-900/60 hover:border-zinc-500'
                                    }`}
                                >
                                    <div className="text-xs text-zinc-400 uppercase tracking-wider mb-1">Pane {idx + 1}</div>
                                    <div className="text-sm text-zinc-200 font-medium truncate">{pane.symbol || 'No symbol selected'}</div>
                                    <div className="text-xs text-zinc-500 mt-1">{pane.dataType ? pane.dataType.replace(/_/g, ' ') : 'No data type'}</div>
                                    <div className="text-xs text-zinc-500 mt-1">{pane.timeframe} | {pane.dataPoints.length} points</div>
                                </button>
                            );
                        })}
                    </div>
                </div>

                <div className="bg-zinc-900/30 border border-zinc-800 rounded-lg p-4 mb-6">
                    <div className="text-xs text-zinc-400 uppercase tracking-wider font-semibold mb-3">Indicators (Active Pane)</div>
                    <div className="flex flex-wrap gap-2">
                        {INDICATOR_OPTIONS.map(option => {
                            const active = currentPane.selectedIndicators.includes(option.key);
                            return (
                                <button
                                    key={option.key}
                                    type="button"
                                    onClick={() => toggleIndicator(option.key)}
                                    disabled={indicatorsDisabled}
                                    className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-all disabled:opacity-50 disabled:cursor-not-allowed ${
                                        active
                                            ? 'bg-emerald-500/20 border-emerald-500 text-emerald-300'
                                            : 'bg-zinc-900 border-zinc-700 text-zinc-300 hover:border-zinc-500'
                                    }`}
                                >
                                    {option.label}
                                </button>
                            );
                        })}
                    </div>
                </div>

                {/* Control Buttons and Status */}
                <div className="flex items-center justify-between gap-4">
                    <div className="flex gap-2">
                        {!isPlaying && !isLoading && replayMode === 'stream' ? (
                            <button onClick={startReplay} className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-5 py-2.5 rounded-lg font-medium transition-all active:scale-95 shadow-lg shadow-emerald-500/20">
                                <Play size={18} fill="currentColor" /> Play
                            </button>
                        ) : isPlaying ? (
                            <button onClick={stopReplay} className="flex items-center gap-2 bg-rose-600 hover:bg-rose-500 text-white px-5 py-2.5 rounded-lg font-medium transition-all active:scale-95 shadow-lg shadow-rose-500/20">
                                <Pause size={18} fill="currentColor" /> Pause
                            </button>
                        ) : isLoading ? (
                            <button disabled className="flex items-center gap-2 bg-zinc-700 text-zinc-200 px-5 py-2.5 rounded-lg font-medium border border-zinc-600">
                                Loading...
                            </button>
                        ) : (
                            <button onClick={loadReplay} className="flex items-center gap-2 bg-cyan-600 hover:bg-cyan-500 text-white px-5 py-2.5 rounded-lg font-medium transition-all active:scale-95 shadow-lg shadow-cyan-500/20">
                                <Play size={18} fill="currentColor" /> Load
                            </button>
                        )}
                        <button onClick={resetReplay} disabled={isPlaying || isLoading} className="flex items-center gap-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-4 py-2.5 rounded-lg border border-zinc-700 transition-all active:scale-95 disabled:opacity-50">
                            <RotateCcw size={18} />
                        </button>
                    </div>

                    <div className="flex items-center justify-between gap-6">
                        <div className="flex items-center gap-3">
                            <div className={`w-2.5 h-2.5 rounded-full ${isPlaying || isLoading ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'}`}></div>
                            <span className="text-sm font-medium text-zinc-300">Active Pane Status: <span className="text-zinc-400">{currentPane.status}</span></span>
                        </div>
                        {totalVisibleRecords > 0 && (
                            <span className="text-sm font-medium text-zinc-300">Total Records: <span className="text-cyan-400 bg-cyan-400/10 px-2 py-0.5 rounded ml-1">{totalVisibleRecords}</span></span>
                        )}
                        <span className="text-sm font-medium text-zinc-300">Points: <span className="text-emerald-400 bg-emerald-400/10 px-2 py-0.5 rounded ml-1">{totalVisiblePoints}</span></span>
                    </div>
                </div>
                    </div>
                </div>
            </div>

            {/* Chart View - Full Width */}
            <div className={`bg-white/5 backdrop-blur-lg border border-white/10 p-6 rounded-2xl shadow-xl w-full flex-1 min-h-0 transition-all duration-300 ${isControlCollapsed ? 'h-[calc(100vh-140px)]' : 'h-[calc(100vh-580px)]'}`}>
                {chartPanes === 1 ? (
                    <div className="h-full rounded-lg border border-white/5 overflow-hidden bg-zinc-900/10">
                        <div className="px-3 py-2 border-b border-white/10 text-xs text-zinc-300 bg-zinc-900/40">
                            Pane 1 | {paneStates[0].symbol || 'No symbol'} | {paneStates[0].dataType || 'No data type'} | {paneStates[0].timeframe} | {paneStates[0].dataPoints.length} points
                        </div>
                        <div className="h-[calc(100%-33px)]">
                            <ChartComponent
                                data={paneStates[0].dataPoints}
                                paneId={0}
                                syncEnabled={syncEnabled}
                                sharedVisibleRange={sharedVisibleRange}
                                onVisibleRangeChange={handleVisibleRangeChange}
                                sharedHoverTime={sharedHoverTime}
                                onHoverTimeChange={handleHoverTimeChange}
                            />
                        </div>
                    </div>
                ) : (
                    <div className={`w-full h-full grid gap-3 ${chartPanes === 2 ? 'grid-cols-1 grid-rows-2' : chartPanes === 3 ? 'grid-cols-1 grid-rows-3' : 'grid-cols-1 lg:grid-cols-2 grid-rows-4 lg:grid-rows-2'}`}>
                        {visiblePaneIndices.map(idx => {
                            const pane = paneStates[idx];
                            const active = idx === activePane;
                            return (
                            <div
                                key={`pane-${idx}`}
                                className={`min-h-0 rounded-lg border overflow-hidden bg-zinc-900/10 cursor-pointer transition-colors ${active ? 'border-emerald-500/70' : 'border-white/5'}`}
                                onClick={() => setActivePane(idx)}
                            >
                                <div className="px-3 py-2 border-b border-white/10 text-xs text-zinc-300 bg-zinc-900/40 flex items-center justify-between">
                                    <span>Pane {idx + 1}{active ? ' (Active)' : ''}</span>
                                    <span className="truncate max-w-[75%] text-right">{pane.symbol || 'No symbol'} | {pane.dataType || 'No data type'} | {pane.timeframe} | {pane.dataPoints.length} points</span>
                                </div>
                                <div className="h-[calc(100%-33px)]">
                                    <ChartComponent
                                        data={pane.dataPoints}
                                        paneId={idx}
                                        syncEnabled={syncEnabled}
                                        sharedVisibleRange={sharedVisibleRange}
                                        onVisibleRangeChange={handleVisibleRangeChange}
                                        sharedHoverTime={sharedHoverTime}
                                        onHoverTimeChange={handleHoverTimeChange}
                                    />
                                </div>
                            </div>
                        );})}
                    </div>
                )}
            </div>
        </div>
    );
}
