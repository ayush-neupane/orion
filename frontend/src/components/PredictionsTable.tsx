/** Per-symbol predictive analysis: upward probability + recommendation. */
import { useMarketStore } from '../store/marketStore';
import { Prediction } from '../types/market';
import { EmptyState, ErrorState, LoadingSpinner } from './States';

function RecommendationBadge({ rec }: { rec: Prediction['recommendation'] }) {
  const style = rec === 'BUY'
    ? 'bg-emerald-500/15 text-emerald-400'
    : rec === 'SELL'
      ? 'bg-rose-500/15 text-rose-400'
      : 'bg-slate-600/30 text-slate-300';
  return (
    <span className={`rounded px-2 py-0.5 text-[10px] font-bold ${style}`}>
      {rec}
    </span>
  );
}

function ProbabilityBar({ prob }: { prob: number }) {
  const pct = Math.round(prob * 100);
  const color = pct >= 58 ? 'bg-emerald-500'
    : pct <= 42 ? 'bg-rose-500' : 'bg-slate-500';
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-800">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-9 text-right text-xs text-slate-300">{pct}%</span>
    </div>
  );
}

export default function PredictionsTable() {
  const { data, loading, error } = useMarketStore((s) => s.predictions);
  const selectSymbol = useMarketStore((s) => s.selectSymbol);
  const selected = useMarketStore((s) => s.selectedSymbol);
  const fetchAll = useMarketStore((s) => s.fetchAll);

  return (
    <section id="predictions" className="rounded-xl border border-slate-800 bg-slate-900/60
      p-4" data-testid="predictions">
      <header className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-300">
          Predictive Analysis Engine</h2>
        <span className="text-[10px] text-slate-500">
          RSI + MACD + Bollinger + News Sentiment (hybrid model)</span>
      </header>
      {loading && <LoadingSpinner label="Running hybrid model…" />}
      {error && <ErrorState message={error} onRetry={() => void fetchAll()} />}
      {!loading && !error && data && data.length === 0 && (
        <EmptyState message="Predictions will appear after the first
          ingestion + model cycle (~1 min after startup)." />
      )}
      {!loading && !error && data && data.length > 0 && (
        <div className="max-h-[320px] overflow-y-auto slim-scroll">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-slate-900">
              <tr className="text-left text-slate-500">
                <th className="pb-2 font-medium">Symbol</th>
                <th className="pb-2 font-medium">P(Up)</th>
                <th className="pb-2 font-medium">Signal</th>
                <th className="pb-2 font-medium">RSI</th>
              </tr>
            </thead>
            <tbody>
              {data.map((p) => (
                <tr key={p.symbol}
                  className={`cursor-pointer border-t border-slate-800/60
                    hover:bg-slate-800/40 ${selected === p.symbol
                      ? 'bg-sky-500/5' : ''}`}
                  onClick={() => selectSymbol(p.symbol)}>
                  <td className="py-1.5 font-semibold text-slate-200">
                    {p.symbol}</td>
                  <td className="py-1.5">
                    <ProbabilityBar prob={p.prob_up} /></td>
                  <td className="py-1.5">
                    <RecommendationBadge rec={p.recommendation} /></td>
                  <td className="py-1.5 text-slate-400">—</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
