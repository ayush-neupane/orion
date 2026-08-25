/**
 * TradingView Lightweight-Charts candlestick wrapper with full
 * loading / error / empty handling and resize support.
 */
import { useEffect, useRef } from 'react';
import {
  CandlestickSeriesPartialOptions, createChart,
  IChartApi, ISeriesApi, UTCTimestamp,
} from 'lightweight-charts';
import { useMarketStore } from '../store/marketStore';
import { ErrorState, LoadingSpinner } from './States';

const CANDLE_STYLE: CandlestickSeriesPartialOptions = {
  upColor: '#22c55e',
  downColor: '#ef4444',
  borderUpColor: '#22c55e',
  borderDownColor: '#ef4444',
  wickUpColor: '#16a34a',
  wickDownColor: '#dc2626',
};

export default function Chart() {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);

  const { data, loading, error } = useMarketStore((s) => s.history);
  const symbol = useMarketStore((s) => s.selectedSymbol);
  const simulated = useMarketStore((s) => s.historySimulated);
  const lastTick = useMarketStore((s) => s.lastTick);
  const moversData = useMarketStore((s) => s.movers.data);
  const fetchAll = useMarketStore((s) => s.fetchAll);

  // Create chart once.
  useEffect(() => {
    if (!containerRef.current || chartRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: { background: { color: '#0f172a' },
        textColor: '#94a3b8' },
      grid: { vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' } },
      timeScale: { timeVisible: false, borderColor: '#1e293b' },
      rightPriceScale: { borderColor: '#1e293b' },
      autoSize: true,
    });
    chartRef.current = chart;
    seriesRef.current = chart.addCandlestickSeries(CANDLE_STYLE);
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  // Push validated history into the series.
  useEffect(() => {
    const series = seriesRef.current;
    if (!series || !data) return;
    series.setData(
      [...data]
        .sort((a, b) => a.time.localeCompare(b.time))
        .map((point) => ({
          time: point.time as unknown as UTCTimestamp,
          open: point.open,
          high: point.high,
          low: point.low,
          close: point.close,
        })),
    );
    chartRef.current?.timeScale().fitContent();
  }, [data]);

  // Real-time layer: merge a live price into the most recent candle so the
  // chart moves between REST polls. Used by both the WS tick stream and the
  // periodic REST quote refresh below.
  const mergeLivePrice = (price: number) => {
    const series = seriesRef.current;
    if (!series || !data || data.length === 0) return;
    if (!Number.isFinite(price) || price <= 0) return;
    const sorted = [...data].sort((a, b) => a.time.localeCompare(b.time));
    const last = sorted[sorted.length - 1];
    if (!last) return;
    // Local-calendar date of the live tick (YYYY-MM-DD).
    const today = new Date().toLocaleDateString('en-CA');
    if (last.time > today) return; // future-dated bar — never rewind it
    if (last.time === today) {
      // Same session — morph the existing candle in place.
      series.update({
        time: last.time as unknown as UTCTimestamp,
        open: last.open,
        high: Math.max(last.high, price),
        low: Math.min(last.low, price),
        close: price,
      });
    } else {
      // The newest stored bar predates the live session (weekend gap, or an
      // upstream daily feed still serving the previous close) — open a
      // forming candle for today instead of mutating the stale one.
      series.update({
        time: today as unknown as UTCTimestamp,
        open: price,
        high: price,
        low: price,
        close: price,
      });
    }
  };

  // Layer 1 — live WS ticks (sub-second latency when connected).
  useEffect(() => {
    if (!lastTick || lastTick.symbol !== symbol) return;
    mergeLivePrice(lastTick.price);
  }); // eslint-disable-line react-hooks/exhaustive-deps

  // Layer 2 — REST quote refreshes (90s poll) keep the candle fresh even
  // when the WebSocket is unavailable.
  useEffect(() => {
    if (!moversData || !symbol) return;
    const all = [...moversData.gainers, ...moversData.losers,
      ...moversData.most_active];
    const quote = all.find((q) => q.symbol === symbol);
    if (quote) mergeLivePrice(quote.price);
  }, [moversData, symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <section id="chart" className="rounded-xl border border-slate-800 bg-slate-900/60 p-4"
      data-testid="chart-panel">
      <header className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold tracking-wide text-slate-300">
          {symbol ? `${symbol} · Daily Candles` : 'Select a stock'}
        </h2>
        {simulated && (
          <span className="rounded bg-amber-500/15 px-2 py-0.5 text-[10px]
            font-medium text-amber-400" title="Live feed unavailable -
            showing deterministic simulated bars">
            SIMULATED FEED
          </span>
        )}
        {!simulated && lastTick?.symbol === symbol && (
          <span className="flex items-center gap-1.5 rounded bg-emerald-500/10
            px-2 py-0.5 text-[10px] font-bold tracking-wider
            text-emerald-400" data-testid="chart-live-badge"
            title="Streaming live updates over WebSocket">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full
              bg-emerald-400" aria-hidden />
            LIVE
          </span>
        )}
      </header>
      <div className="relative h-[340px] w-full">
        <div ref={containerRef} className="absolute inset-0" />
        {loading && (
          <div className="absolute inset-0 bg-slate-950/70">
            <LoadingSpinner label={`Loading ${symbol ?? ''} candles…`} />
          </div>
        )}
        {!loading && error && (
          <div className="absolute inset-0 bg-slate-950/85">
            <ErrorState message={error} onRetry={() => void fetchAll()} />
          </div>
        )}
        {!loading && !error && (!data || data.length === 0) && (
          <div className="absolute inset-0 flex items-center justify-center">
            <p className="text-xs text-slate-500">No price history available.</p>
          </div>
        )}
      </div>
    </section>
  );
}
