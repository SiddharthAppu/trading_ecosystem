'use client';

import { useState } from 'react';
import DownloaderForm from '@/components/DownloaderForm';
import LiveRecorderDashboard from '@/components/LiveRecorderDashboard';
import ReplayControl from '@/components/ReplayControl';
import DBManagementPanel from '@/components/DBManagementPanel';
import { Activity, LayoutDashboard, MonitorPlay, Info, ServerCog } from 'lucide-react';

export default function Home() {
  const [activeTab, setActiveTab] = useState<'control' | 'replay' | 'db'>('control');

  return (
    <main className="min-h-screen bg-zinc-950 text-white selection:bg-indigo-500/30 font-sans transition-colors duration-500">

      {/* Dynamic Background */}
      <div className="fixed inset-0 z-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-indigo-900/10 via-zinc-950 to-emerald-900/5 pointer-events-none"></div>

      <div className={`relative z-10 mx-auto px-6 py-8 transition-all duration-500 ${activeTab === 'replay' ? 'max-w-full' : 'max-w-[1400px]'}`}>
        <header className="mb-8 flex flex-col md:flex-row md:items-center justify-between gap-6 border-b border-white/5 pb-8">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl shadow-lg shadow-indigo-500/20">
              <Activity size={24} className="text-white" />
            </div>
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-white to-zinc-400">
                F&O Data Platform
              </h1>
              <p className="text-zinc-500 text-xs font-bold uppercase tracking-widest mt-1">Institutional Grade Analysis</p>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="flex bg-white/5 p-1 rounded-2xl border border-white/10 backdrop-blur-md">
            <button
              onClick={() => setActiveTab('control')}
              className={`flex items-center gap-2 px-6 py-3 rounded-xl text-sm font-bold transition-all duration-300 ${activeTab === 'control' ? 'bg-indigo-500 text-white shadow-lg shadow-indigo-500/30' : 'text-zinc-500 hover:text-zinc-300 hover:bg-white/5'}`}
            >
              <LayoutDashboard size={18} />
              Control Center
            </button>
            <button
              onClick={() => setActiveTab('replay')}
              className={`flex items-center gap-2 px-6 py-3 rounded-xl text-sm font-bold transition-all duration-300 ${activeTab === 'replay' ? 'bg-indigo-500 text-white shadow-lg shadow-indigo-500/30' : 'text-zinc-500 hover:text-zinc-300 hover:bg-white/5'}`}
            >
              <MonitorPlay size={18} />
              Replay Studio
            </button>
            <button
              onClick={() => setActiveTab('db')}
              className={`flex items-center gap-2 px-6 py-3 rounded-xl text-sm font-bold transition-all duration-300 ${activeTab === 'db' ? 'bg-indigo-500 text-white shadow-lg shadow-indigo-500/30' : 'text-zinc-500 hover:text-zinc-300 hover:bg-white/5'}`}
            >
              <ServerCog size={18} />
              DB Management
            </button>
          </div>
        </header>

        <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
          {activeTab === 'control' ? (
            <div className="grid grid-cols-1 lg:grid-cols-[450px_1fr] gap-8 items-start">
              <div className="flex flex-col gap-6">
                <LiveRecorderDashboard />
                <DownloaderForm />
              </div>

              <div className="space-y-6">
                <div className="bg-white/5 backdrop-blur-lg border border-white/10 p-8 rounded-3xl shadow-xl relative overflow-hidden group">
                  <div className="absolute top-0 right-0 p-8 opacity-10 group-hover:opacity-20 transition-opacity">
                    <Info size={120} />
                  </div>
                  <div className="relative z-10">
                    <h3 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
                      <div className="w-2 h-8 bg-indigo-500 rounded-full"></div>
                      Getting Started
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div className="p-5 bg-black/20 border border-white/5 rounded-2xl space-y-3">
                        <p className="text-xs font-bold text-indigo-400 uppercase tracking-widest">Step 1: Connection</p>
                        <p className="text-sm text-zinc-400 leading-relaxed">Ensure your local database and environment variables are active. Click the Fyers login to authenticate your session.</p>
                      </div>
                      <div className="p-5 bg-black/20 border border-white/5 rounded-2xl space-y-3">
                        <p className="text-xs font-bold text-emerald-400 uppercase tracking-widest">Step 2: Acquisition</p>
                        <p className="text-sm text-zinc-400 leading-relaxed">Use the **Smart Chain** tool to fetch 42 symbols at once. The system handles ATM calculation and Greek processing automatically.</p>
                      </div>
                      <div className="p-5 bg-black/20 border border-white/5 rounded-2xl space-y-3">
                        <p className="text-xs font-bold text-amber-400 uppercase tracking-widest">Step 3: Recording</p>
                        <p className="text-sm text-zinc-400 leading-relaxed">Toggle the Live Recorder to start capturing real-time tick data. Subscribed symbols appear instantly in your workspace.</p>
                      </div>
                      <div className="p-5 bg-black/20 border border-white/5 rounded-2xl space-y-3">
                        <p className="text-xs font-bold text-purple-400 uppercase tracking-widest">Step 4: Analysis</p>
                        <p className="text-sm text-zinc-400 leading-relaxed">Switch to the **Replay Studio** tab to backtest your strategies on full-screen professional charts.</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ) : activeTab === 'replay' ? (
            <div className="w-full">
              <ReplayControl />
            </div>
          ) : (
            <div className="w-full max-w-[1400px]">
              <DBManagementPanel />
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
