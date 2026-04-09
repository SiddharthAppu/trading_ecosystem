'use client';

import { useState, useEffect } from 'react';

// Utility to ensure date is in YYYY-MM-DD format
function toISODate(val: string): string {
    if (/^\d{4}-\d{2}-\d{2}$/.test(val)) return val;
    // Try to convert DD-MM-YYYY or D-M-YYYY to YYYY-MM-DD
    const m = val.match(/^(\d{2})-(\d{2})-(\d{4})$/);
    if (m) return `${m[3]}-${m[2]}-${m[1]}`;
    return val;
}

import axios from 'axios';
import { ShieldCheck, Calendar, Target, Settings, Info } from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8080";

function getErrorMessage(error: unknown): string {
    if (axios.isAxiosError(error)) {
        const detail = error.response?.data?.detail;
        if (typeof detail === 'string' && detail.trim()) {
            return detail;
        }
        return error.message;
    }
    if (error instanceof Error) {
        return error.message;
    }
    return 'Unknown error';
}

export default function DownloaderForm() {
    // Move startDate/endDate above indexStartDate/indexEndDate to avoid ReferenceError
    const [startDate, setStartDate] = useState('2026-03-01');
    const [endDate, setEndDate] = useState('2026-03-07');
    // Index OHLCV download state
    const [indexStatus, setIndexStatus] = useState("");
    const [indexLoading, setIndexLoading] = useState(false);
    const [indexStartDate, setIndexStartDate] = useState('2026-03-01');
    const [indexEndDate, setIndexEndDate] = useState('2026-03-07');

    // Always enforce YYYY-MM-DD format for indexStartDate and indexEndDate
    useEffect(() => {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(indexStartDate)) {
            const fixed = toISODate(indexStartDate);
            if (/^\d{4}-\d{2}-\d{2}$/.test(fixed)) setIndexStartDate(fixed);
        }
        if (!/^\d{4}-\d{2}-\d{2}$/.test(indexEndDate)) {
            const fixed = toISODate(indexEndDate);
            if (/^\d{4}-\d{2}-\d{2}$/.test(fixed)) setIndexEndDate(fixed);
        }
    }, [indexStartDate, indexEndDate]);

        const handleIndexDownload = async (e?: React.FormEvent) => {
            if (e) e.preventDefault();
            setIndexLoading(true);
            setIndexStatus("Downloading NIFTY50 index OHLCV...");
            try {
                const response = await axios.post(`${API_BASE}/index-ohlcv/download`, {
                    symbol: 'NSE:NIFTY50-INDEX',
                    start_date: indexStartDate,
                    end_date: indexEndDate,
                    provider: 'fyers'
                });
                setIndexStatus(response.data.message || "Success");
            } catch (error: unknown) {
                setIndexStatus("Error: " + getErrorMessage(error));
            } finally {
                setIndexLoading(false);
            }
        };
    const [optionSymbol, setOptionSymbol] = useState('NSE:NIFTY26MAR24500CE');
    const [underlyingSymbol, setUnderlyingSymbol] = useState('NSE:NIFTY50-INDEX');
    const [strike, setStrike] = useState('24500');
    const [optionType, setOptionType] = useState('CE');
    const [expiryDate, setExpiryDate] = useState('2026-03-30');

    const [status, setStatus] = useState('');
    const [loading, setLoading] = useState(false);
    const [isSmartLoading, setIsSmartLoading] = useState(false);
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const [summary, setSummary] = useState<{
        totalSymbols: number;
        totalCandles: number;
        strikes: string[];
        dateRange: string;
    } | null>(null);

    useEffect(() => {
        axios.get(`${API_BASE}/auth/status`)
            .then(res => setIsAuthenticated(res.data.authenticated))
            .catch(() => {
                setIsAuthenticated(false);
                setStatus(`Data Collector API is unreachable at ${API_BASE}.`);
            });
    }, []);

    const handleLogin = async () => {
        try {
            const res = await axios.get(`${API_BASE}/auth/url`);
            window.location.href = res.data.url;
        } catch (error) {
            console.error("Login redirect failed", error);
            setStatus("Failed to fetch Fyers login URL.");
        }
    };

    const handleDownload = async (e?: React.FormEvent) => {
        if (e) e.preventDefault();
        setLoading(true);
        setStatus('Downloading and processing data...');
        setSummary(null);
        try {
            const response = await axios.post(`${API_BASE}/download`, {
                option_symbol: optionSymbol,
                underlying_symbol: underlyingSymbol,
                start_date: startDate,
                end_date: endDate,
                strike: parseFloat(strike),
                option_type: optionType,
                expiry_date: expiryDate
            });
            setStatus(response.data.message);
            return true;
        } catch (error: unknown) {
            console.error(error);
            const errorMsg = getErrorMessage(error);
            setStatus(`Error: ${errorMsg}`);
            const unauthorized = axios.isAxiosError(error) && error.response?.status === 401;
            if (errorMsg.includes("authenticate") || errorMsg.includes("-16") || unauthorized) {
                setIsAuthenticated(false);
            }
            return false;
        } finally {
            setLoading(false);
        }
    };

    const handleSmartDownload = async () => {
        setIsSmartLoading(true);
        setStatus("Generating Option Chain...");
        setSummary(null);
        try {
            const expiryPartMatch = optionSymbol.match(/NSE:(?:NIFTY|BANKNIFTY)(\w+)\d{5}/);
            const expiryPart = expiryPartMatch ? expiryPartMatch[1] : "26MAR";

            const genRes = await axios.post(`${API_BASE}/chain/generate`, {
                underlying_symbol: underlyingSymbol,
                expiry_date: expiryPart,
                strike_count: 10
            });

            if (genRes.data.status !== "success") throw new Error("Failed to generate chain");

            const { atm, symbols } = genRes.data.data;
            const total = symbols.length;
            setStatus(`Found ATM ${atm}. Starting bulk download for ${total} symbols...`);

            let totalCandles = 0;
            const uniqueStrikes = new Set<string>();

            for (let i = 0; i < symbols.length; i++) {
                const symbol = symbols[i];
                const strikeMatch = symbol.match(/(\d+)(CE|PE)$/);
                const s = strikeMatch ? strikeMatch[1] : strike;
                const t = strikeMatch ? strikeMatch[2] : optionType;

                if (strikeMatch) uniqueStrikes.add(strikeMatch[1]);

                setStatus(`[${i + 1}/${total}] Downloading ${symbol}...`);
                const res = await axios.post(`${API_BASE}/download`, {
                    option_symbol: symbol,
                    underlying_symbol: underlyingSymbol,
                    start_date: startDate,
                    end_date: endDate,
                    strike: parseFloat(s),
                    option_type: t,
                    expiry_date: expiryDate
                });
                totalCandles += (res.data.count || 0);
            }

            setSummary({
                totalSymbols: total,
                totalCandles: totalCandles,
                strikes: symbols,
                dateRange: `${startDate} to ${endDate}`
            });
            setStatus(`Successfully downloaded all ${total} symbols in the chain!`);
        } catch (error: unknown) {
            console.error(error);
            setStatus("Bulk download failed: " + getErrorMessage(error));
        } finally {
            setIsSmartLoading(false);
        }
    };

    return (
        <div className="bg-white/5 backdrop-blur-lg border border-white/10 p-6 rounded-2xl shadow-xl w-full max-w-md space-y-6">
            <div className="flex items-center justify-between">
                <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
                    <Target className="text-blue-400" size={20} />
                    Data Downloader
                </h2>
                <div className="group relative">
                    <Info size={16} className="text-zinc-500 cursor-help" />
                    <div className="absolute right-0 top-6 w-64 p-3 bg-zinc-900 border border-white/10 rounded-xl text-[10px] text-zinc-400 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50 shadow-2xl">
                        Fetches 1-minute OHLCV data from Fyers and calculates Greeks automatically using Black-Scholes.
                    </div>
                </div>
            </div>

            <form onSubmit={handleDownload} className="space-y-4">
                                {/* section: Index OHLCV Download */}
                                <div className="p-4 bg-indigo-500/5 border border-indigo-500/10 rounded-xl space-y-3">
                                    <div className="text-[10px] uppercase font-bold text-indigo-400/80 tracking-widest flex items-center gap-1">
                                        <ShieldCheck size={12} /> NIFTY50 Index OHLCV
                                    </div>
                                    <div className="grid grid-cols-2 gap-3">
                                        <div className="flex flex-col gap-1">
                                            <label className="text-[10px] text-zinc-500 uppercase font-semibold">Start Date</label>
                                            <input type="date" value={indexStartDate} onChange={e => setIndexStartDate(e.target.value)}
                                                className="bg-black/40 border border-white/5 text-xs text-indigo-100 rounded-lg px-3 py-2 focus:border-indigo-500 focus:outline-none transition-all" />
                                        </div>
                                        <div className="flex flex-col gap-1">
                                            <label className="text-[10px] text-zinc-500 uppercase font-semibold">End Date</label>
                                            <input type="date" value={indexEndDate} onChange={e => setIndexEndDate(e.target.value)}
                                                className="bg-black/40 border border-white/5 text-xs text-indigo-100 rounded-lg px-3 py-2 focus:border-indigo-500 focus:outline-none transition-all" />
                                        </div>
                                    </div>
                                    <button type="button" onClick={handleIndexDownload} disabled={indexLoading}
                                        className={`w-full mt-3 py-3 rounded-xl font-bold shadow-lg transition-all active:scale-95 ${indexLoading ? 'bg-zinc-700 text-zinc-400 cursor-not-allowed' : 'bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-500 hover:to-blue-500 text-white'}`}>
                                        {indexLoading ? 'Processing...' : 'Download NIFTY50 Index OHLCV'}
                                    </button>
                                    {indexStatus && <div className="text-xs mt-2 text-indigo-300">{indexStatus}</div>}
                                </div>
                {/* section: Symbols */}
                <div className="p-4 bg-blue-500/5 border border-blue-500/10 rounded-xl space-y-3">
                    <div className="text-[10px] uppercase font-bold text-blue-400/80 tracking-widest flex items-center gap-1">
                        <Target size={12} /> Asset Target
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div className="flex flex-col gap-1">
                            <label className="text-[10px] text-zinc-500 uppercase font-semibold">Option Symbol</label>
                            <input value={optionSymbol} onChange={e => setOptionSymbol(e.target.value)}
                                className="bg-black/40 border border-white/5 text-xs text-blue-100 rounded-lg px-3 py-2 focus:border-blue-500 focus:outline-none transition-all" />
                        </div>
                        <div className="flex flex-col gap-1">
                            <label className="text-[10px] text-zinc-500 uppercase font-semibold">Underlying</label>
                            <input value={underlyingSymbol} onChange={e => setUnderlyingSymbol(e.target.value)}
                                className="bg-black/40 border border-white/5 text-xs text-blue-100 rounded-lg px-3 py-2 focus:border-blue-500 focus:outline-none transition-all" />
                        </div>
                    </div>
                </div>

                {/* section: Range */}
                <div className="p-4 bg-emerald-500/5 border border-emerald-500/10 rounded-xl space-y-3">
                    <div className="text-[10px] uppercase font-bold text-emerald-400/80 tracking-widest flex items-center gap-1">
                        <Calendar size={12} /> Time Range
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div className="flex flex-col gap-1">
                            <label className="text-[10px] text-zinc-500 uppercase font-semibold">Start Date</label>
                            <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)}
                                className="bg-black/40 border border-white/5 text-xs [&::-webkit-calendar-picker-indicator]:invert text-emerald-100 rounded-lg px-3 py-2 focus:border-emerald-500 focus:outline-none transition-all" />
                        </div>
                        <div className="flex flex-col gap-1">
                            <label className="text-[10px] text-zinc-500 uppercase font-semibold">End Date</label>
                            <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)}
                                className="bg-black/40 border border-white/5 text-xs [&::-webkit-calendar-picker-indicator]:invert text-emerald-100 rounded-lg px-3 py-2 focus:border-emerald-500 focus:outline-none transition-all" />
                        </div>
                    </div>
                </div>

                {/* section: Specs */}
                <div className="p-4 bg-amber-500/5 border border-amber-500/10 rounded-xl space-y-3">
                    <div className="text-[10px] uppercase font-bold text-amber-400/80 tracking-widest flex items-center gap-1">
                        <Settings size={12} /> Contract Specs
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                        <div className="flex flex-col gap-1">
                            <label className="text-[10px] text-zinc-500 uppercase font-semibold">Strike</label>
                            <input value={strike} onChange={e => setStrike(e.target.value)}
                                className="bg-black/40 border border-white/5 text-xs text-amber-100 rounded-lg px-3 py-2 focus:border-amber-500 focus:outline-none transition-all" />
                        </div>
                        <div className="flex flex-col gap-1">
                            <label className="text-[10px] text-zinc-500 uppercase font-semibold">Type</label>
                            <select value={optionType} onChange={e => setOptionType(e.target.value)}
                                className="bg-black/40 border border-white/5 text-xs text-amber-100 rounded-lg px-3 py-2 focus:border-amber-500 focus:outline-none transition-all">
                                <option value="CE">CE</option>
                                <option value="PE">PE</option>
                            </select>
                        </div>
                        <div className="flex flex-col gap-1">
                            <label className="text-[10px] text-zinc-500 uppercase font-semibold">Expiry</label>
                            <input type="date" value={expiryDate} onChange={e => setExpiryDate(e.target.value)}
                                className="bg-black/40 border border-white/5 text-xs [&::-webkit-calendar-picker-indicator]:invert text-amber-100 rounded-lg px-3 py-2 focus:border-amber-500 focus:outline-none transition-all" />
                        </div>
                    </div>
                </div>

                {!isAuthenticated ? (
                    <button type="button" onClick={handleLogin}
                        className="w-full py-4 rounded-xl font-bold shadow-lg transition-all active:scale-95 bg-gradient-to-r from-orange-600 to-amber-600 hover:from-orange-500 hover:to-amber-500 text-white flex items-center justify-center gap-2">
                        Login to Fyers via App
                    </button>
                ) : (
                    <div className="space-y-3">
                        <button type="submit" disabled={loading || isSmartLoading}
                            className={`w-full py-4 rounded-xl font-bold shadow-lg transition-all active:scale-95 ${loading ? 'bg-zinc-700 text-zinc-400 cursor-not-allowed' : 'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white'}`}>
                            {loading ? 'Processing...' : 'Download Single Contract'}
                        </button>

                        <div className="relative flex items-center py-2">
                            <div className="flex-grow border-t border-white/5"></div>
                            <span className="flex-shrink mx-4 text-[10px] text-zinc-600 font-bold uppercase tracking-[0.2em]">or</span>
                            <div className="flex-grow border-t border-white/5"></div>
                        </div>

                        <button type="button" onClick={handleSmartDownload} disabled={isSmartLoading || loading}
                            className="w-full bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 py-4 rounded-xl font-bold flex flex-col items-center justify-center gap-1 transition-all group relative overflow-hidden">
                            <div className="flex items-center gap-2">
                                {isSmartLoading ? <div className="w-4 h-4 border-2 border-indigo-400/30 border-t-indigo-400 rounded-full animate-spin" /> : <ShieldCheck size={18} />}
                                <span>Bulk Download Entire Chain</span>
                            </div>
                            <span className="text-[9px] opacity-60 font-medium">Automatic ATM +/- 10 Strikes</span>
                        </button>
                    </div>
                )}
            </form>

            {summary && (
                <div className="mt-4 p-4 rounded-xl bg-indigo-500/10 border border-indigo-500/20 animate-in fade-in zoom-in duration-300">
                    <div className="flex items-center gap-2 mb-3">
                        <ShieldCheck className="text-indigo-400" size={16} />
                        <h3 className="text-sm font-bold text-white uppercase tracking-wider">Bulk Download Summary</h3>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-1">
                            <p className="text-[10px] text-zinc-500 uppercase font-bold">Total Symbols</p>
                            <p className="text-lg font-mono text-indigo-100">{summary.totalSymbols}</p>
                        </div>
                        <div className="space-y-1">
                            <p className="text-[10px] text-zinc-500 uppercase font-bold">Total Candles</p>
                            <p className="text-lg font-mono text-emerald-400">{summary.totalCandles.toLocaleString()}</p>
                        </div>
                        <div className="col-span-2 space-y-2">
                            <p className="text-[10px] text-zinc-500 uppercase font-bold">Strike List</p>
                            <div className="flex flex-wrap gap-1.5 max-h-[100px] overflow-y-auto p-2 bg-black/30 rounded-lg border border-white/5 custom-scrollbar">
                                {summary.strikes.map(s => (
                                    <span key={s} className="px-2 py-0.5 bg-indigo-500/20 text-indigo-200 text-[10px] font-mono rounded border border-indigo-500/30">
                                        {s}
                                    </span>
                                ))}
                            </div>
                            <p className="text-[9px] text-zinc-600 italic">Total: {summary.strikes.length} unique strikes (CE + PE available for each)</p>
                        </div>
                        <div className="col-span-2 space-y-1">
                            <p className="text-[10px] text-zinc-500 uppercase font-bold">Date Range</p>
                            <p className="text-xs font-mono text-zinc-300">{summary.dateRange}</p>
                        </div>
                    </div>
                </div>
            )}

            {status && !summary && (
                <div className="mt-4 p-4 rounded-xl bg-black/40 border border-white/5 animate-in fade-in slide-in-from-top-2">
                    <p className={`text-xs font-medium leading-relaxed ${status.includes('Error') || status.includes('failed') ? 'text-red-400' : 'text-emerald-400'}`}>
                        {status}
                    </p>
                </div>
            )}
        </div>
    );
}
