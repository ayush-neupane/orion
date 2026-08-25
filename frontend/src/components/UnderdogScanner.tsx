/** "The Underdog Scanner": low P/E + rising volume + positive sentiment
 *  candidates, ranked by Potential Breakout score (1-100). */
import { motion } from 'framer-motion';
import { useMarketStore } from '../store/marketStore';
import { EmptyState, ErrorState, LoadingSpinner } from './States';

function ScoreBar({ score }: { score: number }) {
  const color = score >= 75 ? 'bg-emerald-500'
    : score >= 55 ? 'bg-sky-500' : 'bg-slate-600';
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-800">
        <motion.div className={`h-full ${color}`}
          initial={{ width: 0 }} animate={{ width: `${score}%` }}
          transition={{ duration: 0.7 }} />
      </div>
      <span className="w-7 text-right text-xs text-slate-300">{score}</span>
    </div>
  );
}

export default function UnderdogScanner() {
  const { data, loading, error } = useMarketStore((s) => s.underdogs);
  const selectSymbol = useMarketStore((s) => s.selectSymbol);
  const fetchAll = useMarketStore((s) => s.fetchAll);

  return (
    <section id="underdogs" className="rounded-xl border border-slate-800 bg-slate-900/60
      p-4" data-testid="underdogs">
      <header className="mb-3 flex items-center gap-2">
        <span className="text-base">🕵️</span>
        <h2 className="text-sm font-semibold text-slate-300">
          The Underdog Scanner</h2>
        <span className="rounded bg-purple-500/15 px-2 py-0.5 text-[10px]
          text-purple-300">Potential Breakout</span>
      </header>
      {loading && <LoadingSpinner label="Scanning for underdogs…" />}
      {error && <ErrorState message={error} onRetry={() => void fetchAll()} />}
      {!loading && !error && data && data.length === 0 && (
        <EmptyState message="No breakout candidates above threshold in
          this market right now." />
      )}
      {!loading && !error && data && data.length > 0 && (
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-slate-500">
              <th className="pb-2 font-medium">Symbol</th>
              <th className="pb-2 font-medium">P/E</th>
              <th className="pb-2 font-medium">Vol 3d</th>
              <th className="pb-2 font-medium">Sentiment</th>
              <th className="pb-2 font-medium">Breakout</th>
            </tr>
          </thead>
          <tbody>
            {data.map((p) => (
              <tr key={p.symbol}
                className="cursor-pointer border-t border-slate-800/60
                  hover:bg-slate-800/40"
                onClick={() => selectSymbol(p.symbol)}>
                <td className="py-1.5 font-semibold text-slate-200">
                  {p.symbol}</td>
                <td className="py-1.5 text-slate-400">
                  {p.pe_ratio != null ? p.pe_ratio.toFixed(1) : '—'}</td>
                <td className={`py-1.5 ${p.volume_trend_3d >= 0
                  ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {p.volume_trend_3d >= 0 ? '+' : ''}
                  {p.volume_trend_3d.toFixed(0)}%</td>
                <td className={`py-1.5 ${p.sentiment_score > 0.1
                  ? 'text-emerald-400' : p.sentiment_score < -0.1
                    ? 'text-rose-400' : 'text-slate-400'}`}>
                  {p.sentiment_score > 0.1 ? 'Bullish'
                    : p.sentiment_score < -0.1 ? 'Bearish' : 'Neutral'}</td>
                <td className="py-1.5"><ScoreBar score={p.breakout_score} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
