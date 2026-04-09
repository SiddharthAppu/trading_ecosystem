"use client";

import { useState, useEffect } from 'react';
import { Play, Square, Plus, Trash2, Database, ShieldCheck, Info } from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8080";

type IndexTick = {
  time: string;
  price: number;
  volume: number;
  bid_price: number;
  ask_price: number;
};

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return 'Unknown error';
}

export default function LiveRecorderDashboard() {
    // Live index ticks state
    const [indexTicks, setIndexTicks] = useState<IndexTick[]>([]);
    const [indexTicksLoading, setIndexTicksLoading] = useState(false);
  const [backendError, setBackendError] = useState<string | null>(null);

    // Fetch recent index ticks every 5s
    useEffect(() => {
      let mounted = true;
      const fetchIndexTicks = async () => {
        setIndexTicksLoading(true);
        try {
          const res = await fetch(`${API_BASE}/index-ticks/recent?limit=20`);
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const data = await res.json();
          if (mounted && data.status === "success") {
            setIndexTicks(data.ticks);
            setBackendError(null);
          }
        } catch {
          if (mounted) setIndexTicks([]);
        } finally {
          if (mounted) setIndexTicksLoading(false);
        }
      };
      fetchIndexTicks();
      const interval = setInterval(fetchIndexTicks, 5000);
      return () => { mounted = false; clearInterval(interval); };
    }, []);
  const [isRunning, setIsRunning] = useState(false);
  const [symbols, setSymbols] = useState<string[]>([]);
  const [newSymbol, setNewSymbol] = useState("");
  const [loading, setLoading] = useState(false);

  // Smart Chain State
  const [expiryDate, setExpiryDate] = useState("26MAR");
  const [underlying, setUnderlying] = useState("NSE:NIFTY50-INDEX");
  const [isSmartLoading, setIsSmartLoading] = useState(false);
  const [activity, setActivity] = useState<{ ticks: number, symbols: number, timestamp: string }[]>([]);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);

    // SSE for Live Activity
    const eventSource = new EventSource(`${API_BASE}/recorder/events`);
    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "save") {
        setActivity(prev => [{
          ticks: data.ticks,
          symbols: data.symbols,
          timestamp: new Date().toLocaleTimeString()
        }, ...prev].slice(0, 5)); // Keep last 5 events
      }
    };

    return () => {
      clearInterval(interval);
      eventSource.close();
    };
  }, []);

  const fetchStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/recorder/status`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setIsRunning(data.is_running);
      setSymbols(data.symbols);
      setBackendError(null);
    } catch {
      setBackendError(`Data Collector API is unreachable at ${API_BASE}`);
      setIsRunning(false);
      setSymbols([]);
    }
  };

  const toggleRecorder = async () => {
    setLoading(true);
    try {
      const endpoint = isRunning ? "/recorder/stop" : "/recorder/start";
      const res = await fetch(API_BASE + endpoint, { method: 'POST' });
      const data = await res.json();
      if (data.status === "success") {
        setIsRunning(!isRunning);
      } else {
        alert(data.message || "Operation failed");
      }
    } catch {
      alert("Failed to connect to backend");
    } finally {
      setLoading(false);
    }
  };

  const addSymbol = async () => {
    if (!newSymbol) return;
    try {
      const res = await fetch(`${API_BASE}/recorder/subscribe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbols: [newSymbol] })
      });
      const data = await res.json();
      setSymbols(data.symbols);
      setNewSymbol("");
    } catch (err: unknown) {
      alert(getErrorMessage(err));
    }
  };

  const removeSymbol = async (sym: string) => {
    try {
      const res = await fetch(`${API_BASE}/recorder/unsubscribe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbols: [sym] })
      });
      const data = await res.json();
      setSymbols(data.symbols);
    } catch {
      alert("Failed to unsubscribe");
    }
  };

  const handleSmartSubscribe = async () => {
    setIsSmartLoading(true);
    try {
      const genRes = await fetch(`${API_BASE}/chain/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          underlying_symbol: underlying,
          expiry_date: expiryDate,
          strike_count: 10
        })
      });
      const genData = await genRes.json();
      if (genData.status !== "success") throw new Error(genData.detail || "Generation failed");

      const chainSymbols = genData.data.symbols;
      const subRes = await fetch(`${API_BASE}/recorder/subscribe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbols: chainSymbols })
      });
      const subData = await subRes.json();
      setSymbols(subData.symbols);
    } catch (err: unknown) {
      alert(getErrorMessage(err));
    } finally {
      setIsSmartLoading(false);
    }
  };

  return (
    <div className="bg-white/5 backdrop-blur-xl border border-white/10 p-6 rounded-2xl shadow-2xl space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={`p-3 rounded-xl transition-all shadow-lg ${isRunning ? 'bg-emerald-500/20 text-emerald-400 ring-1 ring-emerald-500/50 shadow-emerald-500/20' : 'bg-white/5 text-zinc-500 border border-white/10'}`}>
            <Database size={24} />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white tracking-tight">Live Recorder</h2>
            <div className="flex items-center gap-1.5">
              <div className={`w-1.5 h-1.5 rounded-full animate-pulse ${isRunning ? 'bg-emerald-500' : 'bg-red-500'}`}></div>
              <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">{isRunning ? 'Running' : 'Offline'}</span>
            </div>
          </div>
        </div>
        <button
          onClick={toggleRecorder}
          disabled={loading}
          className={`flex items-center gap-2 px-5 py-3 rounded-xl font-bold transition-all active:scale-95 shadow-lg ${isRunning ? 'bg-red-500/10 text-red-500 border border-red-500/20 hover:bg-red-500/20' : 'bg-emerald-500 text-white hover:bg-emerald-400 shadow-emerald-500/30'}`}
        >
          {loading ? (
            <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin" />
          ) : isRunning ? (
            <>
              <Square size={18} fill="currentColor" /> Stop
            </>
          ) : (
            <>
              <Play size={18} fill="currentColor" /> Start
            </>
          )}
        </button>
      </div>

      <div className="space-y-4">
        {backendError && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-xl">
            <p className="text-xs text-red-300 font-medium">{backendError}</p>
            <p className="text-[10px] text-red-200/80 mt-1">
              Start Data Collector service (port 8080) or set NEXT_PUBLIC_API_BASE correctly.
            </p>
          </div>
        )}

        {/* section: Live NIFTY50 Index Ticks */}
        <div className="p-4 bg-indigo-500/5 border border-indigo-500/10 rounded-xl space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-[10px] uppercase font-bold text-indigo-400/80 tracking-widest flex items-center gap-1">
              <Database size={12} /> NIFTY50 Index Ticks (Live)
            </div>
            <span className="text-[9px] text-zinc-500 font-medium font-mono uppercase">Auto-refresh 5s</span>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-xs text-indigo-100">
              <thead>
                <tr className="text-indigo-300">
                  <th className="px-2 py-1">Time</th>
                  <th className="px-2 py-1">Price</th>
                  <th className="px-2 py-1">Volume</th>
                  <th className="px-2 py-1">Bid</th>
                  <th className="px-2 py-1">Ask</th>
                </tr>
              </thead>
              <tbody>
                {indexTicksLoading ? (
                  <tr><td colSpan={5} className="text-center text-zinc-400 py-2">Loading...</td></tr>
                ) : indexTicks.length === 0 ? (
                  <tr><td colSpan={5} className="text-center text-zinc-400 py-2">No recent ticks</td></tr>
                ) : (
                  indexTicks.map((tick, i) => (
                    <tr key={i} className="border-b border-white/5 last:border-0">
                      <td className="px-2 py-1 font-mono text-[10px]">{new Date(tick.time).toLocaleTimeString()}</td>
                      <td className="px-2 py-1 font-mono">{tick.price}</td>
                      <td className="px-2 py-1 font-mono">{tick.volume}</td>
                      <td className="px-2 py-1 font-mono">{tick.bid_price}</td>
                      <td className="px-2 py-1 font-mono">{tick.ask_price}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
        {/* section: Manual */}
        <div className="p-4 bg-white/5 border border-white/10 rounded-xl space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-[10px] uppercase font-bold text-zinc-400 tracking-widest">Manual Entry</div>
            <div className="group relative">
              <Info size={12} className="text-zinc-600 cursor-help" />
              <div className="absolute right-0 top-4 w-48 p-2 bg-zinc-900 border border-white/10 rounded-lg text-[9px] text-zinc-400 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
                Subscribe to individual symbols by entering full Fyers format (e.g. NSE:NIFTY26MAR24500CE).
              </div>
            </div>
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="NSE:NIFTY50-INDEX"
              value={newSymbol}
              onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
              className="flex-grow bg-black/40 border border-white/5 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-white/20 transition-all placeholder:text-zinc-700"
            />
            <button onClick={addSymbol} className="p-2.5 bg-white/5 hover:bg-white/10 rounded-lg text-white border border-white/10 transition-all"><Plus size={16} /></button>
          </div>
        </div>

        {/* section: Smart */}
        <div className="p-4 bg-indigo-500/5 border border-indigo-500/10 rounded-xl space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-[10px] uppercase font-bold text-indigo-400/80 tracking-widest flex items-center gap-1">
              <ShieldCheck size={12} /> Smart Chain Subscribe
            </div>
            <div className="group relative">
              <Info size={12} className="text-zinc-600 cursor-help" />
              <div className="absolute right-0 top-4 w-48 p-2 bg-zinc-900 border border-white/10 rounded-lg text-[9px] text-zinc-400 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
                Calculates ATM from current spot and subscribes to 21 strikes (CE & PE) instantly.
              </div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <select value={underlying} onChange={(e) => setUnderlying(e.target.value)}
              className="bg-black/40 border border-white/5 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-indigo-500/30 transition-all">
              <option value="NSE:NIFTY50-INDEX">NIFTY 50</option>
              <option value="NSE:NIFTYBANK-INDEX">BANK NIFTY</option>
            </select>
            <div className="flex flex-col gap-1.5">
              <label className="text-[9px] text-zinc-500 font-bold uppercase ml-1">Expiry (e.g. 26MAR or 26312)</label>
              <input type="text" placeholder="26MAR" value={expiryDate} onChange={(e) => setExpiryDate(e.target.value.toUpperCase())}
                className="bg-black/40 border border-white/5 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-indigo-500/30 transition-all placeholder:text-zinc-700" />
            </div>
          </div>
          <button onClick={handleSmartSubscribe} disabled={isSmartLoading}
            className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-700 text-white text-[10px] font-bold py-2.5 rounded-lg transition-all shadow-lg shadow-indigo-500/10 flex items-center justify-center gap-2">
            {isSmartLoading ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Plus size={14} />}
            Auto-Subscribe ATM +/- 10
          </button>
        </div>

        {/* section: Live Activity */}
        {isRunning && (
          <div className="p-4 bg-emerald-500/5 border border-emerald-500/10 rounded-xl space-y-3 animate-in fade-in slide-in-from-top-2">
            <div className="flex items-center justify-between">
              <div className="text-[10px] uppercase font-bold text-emerald-400/80 tracking-widest flex items-center gap-1">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping" />
                Live Activity Pulse
              </div>
              <span className="text-[9px] text-zinc-500 font-medium font-mono uppercase">Database Sync Active</span>
            </div>

            <div className="space-y-2">
              {activity.length === 0 ? (
                <div className="flex flex-col items-center justify-center p-4 border border-dashed border-white/5 rounded-lg gap-2">
                  <div className="w-full h-1 bg-white/5 rounded-full overflow-hidden">
                    <div className="h-full bg-emerald-500/30 w-1/3 animate-progress" />
                  </div>
                  <p className="text-[9px] text-zinc-600">Waiting for next tick batch...</p>
                </div>
              ) : (
                <div className="space-y-1.5">
                  {activity.map((act, i) => (
                    <div key={i} className={`flex items-center justify-between text-[10px] p-2 rounded-lg border border-white/5 bg-white/[0.02] ${i === 0 ? 'border-emerald-500/20 bg-emerald-500/5 animate-pulse-subtle' : 'opacity-60'}`}>
                      <div className="flex items-center gap-2">
                        <Database size={10} className="text-emerald-500" />
                        <span className="text-zinc-300">Saved <span className="font-bold text-emerald-400">{act.ticks}</span> ticks for <span className="text-white">{act.symbols}</span> symbols</span>
                      </div>
                      <span className="text-[9px] text-zinc-600 font-mono">{act.timestamp}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        <div className="space-y-2">
          <div className="text-[10px] uppercase font-bold text-zinc-500 tracking-widest px-1 flex items-center justify-between">
            <span>Active Channels</span>
            <span>{(symbols || []).length} / 50</span>
          </div>
          <div className="bg-black/20 rounded-xl border border-white/5 divide-y divide-white/5 max-h-[250px] overflow-y-auto custom-scrollbar">
            {(symbols || []).length === 0 ? (
              <div className="p-8 text-center text-zinc-600 text-[10px] italic">No active subscriptions</div>
            ) : (
              (symbols || []).map(sym => (
                <div key={sym} className="flex items-center justify-between px-4 py-2.5 bg-white/[0.02] hover:bg-white/[0.05] transition-all group">
                  <span className="text-[11px] text-zinc-300 font-medium font-mono">{sym}</span>
                  <button onClick={() => removeSymbol(sym)} className="opacity-0 group-hover:opacity-100 p-1.5 text-zinc-500 hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-all"><Trash2 size={14} /></button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
