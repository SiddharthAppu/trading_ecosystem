'use client';

import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, Database, RefreshCw, Table2, AlertTriangle } from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8080';

type ColumnInfo = {
  name: string;
  type: string;
  nullable: boolean;
};

type TableSummary = {
  table: string;
  row_count: number;
  time_range: { min: string | null; max: string | null } | null;
  distinct_symbols: number | null;
  gap_analysis:
    | {
        gap_minutes_threshold: number;
        gap_events: number;
        max_gap_minutes: number | null;
      }
    | null;
  columns: ColumnInfo[];
};

type SchemaSummary = {
  schema: string;
  table_count: number;
  tables: TableSummary[];
};

type OverviewResponse = {
  status: string;
  generated_at: string;
  database: string;
  all_databases: string[];
  schemas: SchemaSummary[];
};

type TableDetailResponse = {
  status: string;
  generated_at: string;
  table: {
    schema: string;
    name: string;
    row_count: number;
    time_range: { min: string | null; max: string | null } | null;
    has_time: boolean;
    has_symbol: boolean;
  };
  columns: ColumnInfo[];
  symbol_ranges: {
    symbol: string;
    records: number;
    min_time: string | null;
    max_time: string | null;
  }[];
  gap_analysis:
    | {
        gap_minutes_threshold: number;
        sample_gaps: {
          symbol: string;
          gap_start: string;
          gap_end: string;
          missing_minutes: number;
        }[];
      }
    | null;
  filters?: {
    symbol_query?: string | null;
    from_time?: string | null;
    to_time?: string | null;
  };
};

type TableFilterState = {
  symbolQuery: string;
  fromDate: string;
  toDate: string;
};

function formatTs(value: string | null | undefined): string {
  if (!value) return '-';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString();
}

function formatNum(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-';
  return value.toLocaleString();
}

export default function DBManagementPanel() {
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [gapMinutes, setGapMinutes] = useState(60);
  const [expandedTableKey, setExpandedTableKey] = useState('');
  const [detailByTable, setDetailByTable] = useState<Record<string, TableDetailResponse>>({});
  const [detailLoadingKey, setDetailLoadingKey] = useState('');
  const [filtersByTable, setFiltersByTable] = useState<Record<string, TableFilterState>>({});

  const totals = useMemo(() => {
    if (!overview) return { tables: 0, rows: 0 };
    const allTables = overview.schemas.flatMap((s) => s.tables);
    return {
      tables: allTables.length,
      rows: allTables.reduce((acc, t) => acc + (t.row_count || 0), 0),
    };
  }, [overview]);

  const fetchOverview = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(
        `${API_BASE}/db/overview?schemas=broker_fyers,broker_upstox,analytics&gap_minutes=${gapMinutes}`
      );
      const data = (await res.json()) as OverviewResponse;
      if (!res.ok || data.status !== 'success') {
        throw new Error((data as { detail?: string }).detail || 'Failed to fetch DB overview');
      }
      setOverview(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch DB overview');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOverview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const getTableFilters = (key: string): TableFilterState =>
    filtersByTable[key] ?? { symbolQuery: '', fromDate: '', toDate: '' };

  const setTableFilters = (key: string, patch: Partial<TableFilterState>) => {
    setFiltersByTable((prev) => ({
      ...prev,
      [key]: {
        ...getTableFilters(key),
        ...patch,
      },
    }));
  };

  const loadTableDetail = async (schema: string, table: string, forceReload = false) => {
    const key = `${schema}.${table}`;
    if (!forceReload) {
      setExpandedTableKey((prev) => (prev === key ? '' : key));
      if (detailByTable[key]) return;
    }

    const filter = getTableFilters(key);
    const params = new URLSearchParams({
      schema,
      table,
      gap_minutes: String(gapMinutes),
      symbol_limit: '30',
    });
    if (filter.symbolQuery.trim()) params.set('symbol_query', filter.symbolQuery.trim());
    if (filter.fromDate) params.set('from_time', filter.fromDate);
    if (filter.toDate) params.set('to_time', filter.toDate);

    setDetailLoadingKey(key);
    try {
      const res = await fetch(`${API_BASE}/db/table-detail?${params.toString()}`);
      const data = (await res.json()) as TableDetailResponse;
      if (!res.ok || data.status !== 'success') {
        throw new Error((data as { detail?: string }).detail || 'Failed to fetch table detail');
      }
      setDetailByTable((prev) => ({ ...prev, [key]: data }));
      setExpandedTableKey(key);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch table detail');
    } finally {
      setDetailLoadingKey('');
    }
  };

  return (
    <div className="bg-white/5 backdrop-blur-xl border border-white/10 p-6 rounded-2xl shadow-2xl space-y-5">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
            <Database size={20} />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white tracking-tight">DB Management</h2>
            <p className="text-[11px] text-zinc-500 uppercase tracking-widest">Schema · Counts · Time Ranges · Gaps</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-[11px] text-zinc-400">Gap threshold (min)</label>
          <input
            type="number"
            min={1}
            max={1440}
            value={gapMinutes}
            onChange={(e) => setGapMinutes(Number(e.target.value) || 5)}
            className="w-20 bg-black/40 border border-white/10 rounded-lg px-2 py-1.5 text-xs text-white"
          />
          <button
            onClick={fetchOverview}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-bold bg-cyan-600/20 border border-cyan-500/40 text-cyan-200 hover:bg-cyan-600/30 transition-all disabled:opacity-50"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {overview && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="p-3 rounded-xl bg-black/25 border border-white/10">
            <div className="text-[10px] text-zinc-500 uppercase">Current DB</div>
            <div className="text-sm text-white font-mono mt-1">{overview.database}</div>
          </div>
          <div className="p-3 rounded-xl bg-black/25 border border-white/10">
            <div className="text-[10px] text-zinc-500 uppercase">Known DBs</div>
            <div className="text-sm text-cyan-200 font-mono mt-1">{overview.all_databases.length}</div>
          </div>
          <div className="p-3 rounded-xl bg-black/25 border border-white/10">
            <div className="text-[10px] text-zinc-500 uppercase">Tables</div>
            <div className="text-sm text-emerald-300 font-mono mt-1">{formatNum(totals.tables)}</div>
          </div>
          <div className="p-3 rounded-xl bg-black/25 border border-white/10">
            <div className="text-[10px] text-zinc-500 uppercase">Rows (Total)</div>
            <div className="text-sm text-amber-300 font-mono mt-1">{formatNum(totals.rows)}</div>
          </div>
        </div>
      )}

      {error && (
        <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-300 text-xs flex items-center gap-2">
          <AlertTriangle size={14} />
          {error}
        </div>
      )}

      {loading && <div className="text-xs text-zinc-400">Loading DB overview...</div>}

      {!loading && overview && (
        <div className="space-y-3">
          {overview.schemas.map((schemaBlock) => (
            <details key={schemaBlock.schema} open className="rounded-xl border border-white/10 bg-black/20 overflow-hidden">
              <summary className="cursor-pointer list-none px-4 py-3 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <ChevronDown size={14} className="text-zinc-500" />
                  <span className="font-semibold text-white">{schemaBlock.schema}</span>
                </div>
                <span className="text-[11px] text-zinc-500">{schemaBlock.table_count} table(s)</span>
              </summary>

              <div className="px-3 pb-3 space-y-2">
                {schemaBlock.tables.map((table) => {
                  const key = `${schemaBlock.schema}.${table.table}`;
                  const isExpanded = expandedTableKey === key;
                  const detail = detailByTable[key];
                  const loadingDetail = detailLoadingKey === key;
                  const tableFilter = getTableFilters(key);

                  return (
                    <div key={key} className="rounded-lg border border-white/10 bg-white/[0.02]">
                      <button
                        onClick={() => loadTableDetail(schemaBlock.schema, table.table)}
                        className="w-full text-left px-3 py-2.5 hover:bg-white/[0.04] transition-colors"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="flex items-center gap-2 min-w-0">
                            <Table2 size={14} className="text-zinc-500 shrink-0" />
                            <span className="text-sm text-zinc-100 font-mono truncate">{table.table}</span>
                          </div>
                          <div className="text-[10px] text-zinc-500">{formatNum(table.row_count)} rows</div>
                        </div>
                        <div className="mt-1 text-[10px] text-zinc-500 flex gap-3 flex-wrap">
                          <span>Symbols: {formatNum(table.distinct_symbols)}</span>
                          <span>
                            Time: {formatTs(table.time_range?.min)} to {formatTs(table.time_range?.max)}
                          </span>
                          <span>
                            Gaps: {table.gap_analysis ? formatNum(table.gap_analysis.gap_events) : '-'}
                          </span>
                        </div>
                      </button>

                      {isExpanded && (
                        <div className="border-t border-white/10 px-3 py-3 space-y-3">
                          <div className="rounded-md border border-white/10 bg-black/20 p-3">
                            <div className="text-[11px] text-zinc-400 mb-2">Filters</div>
                            <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
                              <input
                                value={tableFilter.symbolQuery}
                                onChange={(e) => setTableFilters(key, { symbolQuery: e.target.value })}
                                placeholder="Symbol contains..."
                                className="md:col-span-2 bg-black/40 border border-white/10 rounded-lg px-2.5 py-2 text-xs text-white"
                              />
                              <input
                                type="date"
                                value={tableFilter.fromDate}
                                onChange={(e) => setTableFilters(key, { fromDate: e.target.value })}
                                className="bg-black/40 border border-white/10 rounded-lg px-2.5 py-2 text-xs text-white"
                              />
                              <input
                                type="date"
                                value={tableFilter.toDate}
                                onChange={(e) => setTableFilters(key, { toDate: e.target.value })}
                                className="bg-black/40 border border-white/10 rounded-lg px-2.5 py-2 text-xs text-white"
                              />
                            </div>
                            <div className="mt-2 flex items-center gap-2">
                              <button
                                onClick={() => loadTableDetail(schemaBlock.schema, table.table, true)}
                                className="px-3 py-1.5 rounded-lg text-[11px] font-semibold bg-cyan-600/20 border border-cyan-500/40 text-cyan-200 hover:bg-cyan-600/30"
                              >
                                Apply Filters
                              </button>
                              <button
                                onClick={() => {
                                  setTableFilters(key, { symbolQuery: '', fromDate: '', toDate: '' });
                                  loadTableDetail(schemaBlock.schema, table.table, true);
                                }}
                                className="px-3 py-1.5 rounded-lg text-[11px] font-semibold bg-zinc-700/30 border border-white/10 text-zinc-300 hover:bg-zinc-700/50"
                              >
                                Reset
                              </button>
                            </div>
                          </div>

                          {loadingDetail && <div className="text-xs text-zinc-400">Loading details...</div>}
                          {!loadingDetail && detail && (
                            <>
                              {(detail.filters?.symbol_query || detail.filters?.from_time || detail.filters?.to_time) && (
                                <div className="text-[11px] text-zinc-500">
                                  Active filter: symbol={detail.filters?.symbol_query || '-'} | from={formatTs(detail.filters?.from_time || null)} | to={formatTs(detail.filters?.to_time || null)}
                                </div>
                              )}

                              <details open className="rounded-md border border-white/10 bg-black/20">
                                <summary className="cursor-pointer px-3 py-2 text-xs text-cyan-300">Table Schema (Columns)</summary>
                                <div className="px-3 pb-3 overflow-x-auto">
                                  <table className="min-w-full text-xs">
                                    <thead>
                                      <tr className="text-zinc-500">
                                        <th className="text-left py-1">Column</th>
                                        <th className="text-left py-1">Type</th>
                                        <th className="text-left py-1">Nullable</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {detail.columns.map((c) => (
                                        <tr key={c.name} className="border-t border-white/5 text-zinc-300">
                                          <td className="py-1 font-mono">{c.name}</td>
                                          <td className="py-1">{c.type}</td>
                                          <td className="py-1">{c.nullable ? 'YES' : 'NO'}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              </details>

                              <details className="rounded-md border border-white/10 bg-black/20">
                                <summary className="cursor-pointer px-3 py-2 text-xs text-emerald-300">Symbols and Date Ranges</summary>
                                <div className="px-3 pb-3 overflow-x-auto">
                                  {detail.symbol_ranges.length === 0 ? (
                                    <div className="text-xs text-zinc-500">No symbol/time metadata available for this table.</div>
                                  ) : (
                                    <table className="min-w-full text-xs">
                                      <thead>
                                        <tr className="text-zinc-500">
                                          <th className="text-left py-1">Symbol</th>
                                          <th className="text-left py-1">Records</th>
                                          <th className="text-left py-1">From</th>
                                          <th className="text-left py-1">To</th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {detail.symbol_ranges.map((s) => (
                                          <tr key={s.symbol} className="border-t border-white/5 text-zinc-300">
                                            <td className="py-1 font-mono">{s.symbol}</td>
                                            <td className="py-1">{formatNum(s.records)}</td>
                                            <td className="py-1">{formatTs(s.min_time)}</td>
                                            <td className="py-1">{formatTs(s.max_time)}</td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  )}
                                </div>
                              </details>

                              <details className="rounded-md border border-white/10 bg-black/20">
                                <summary className="cursor-pointer px-3 py-2 text-xs text-amber-300">Gap Detection</summary>
                                <div className="px-3 pb-3 overflow-x-auto">
                                  {!detail.gap_analysis || detail.gap_analysis.sample_gaps.length === 0 ? (
                                    <div className="text-xs text-zinc-500">No gaps detected above {gapMinutes} minute(s) in sampled results.</div>
                                  ) : (
                                    <table className="min-w-full text-xs">
                                      <thead>
                                        <tr className="text-zinc-500">
                                          <th className="text-left py-1">Symbol</th>
                                          <th className="text-left py-1">Gap Start</th>
                                          <th className="text-left py-1">Gap End</th>
                                          <th className="text-left py-1">Missing Minutes</th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {detail.gap_analysis.sample_gaps.map((g, i) => (
                                          <tr key={`${g.symbol}-${i}`} className="border-t border-white/5 text-zinc-300">
                                            <td className="py-1 font-mono">{g.symbol}</td>
                                            <td className="py-1">{formatTs(g.gap_start)}</td>
                                            <td className="py-1">{formatTs(g.gap_end)}</td>
                                            <td className="py-1">{g.missing_minutes.toFixed(2)}</td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  )}
                                </div>
                              </details>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}
