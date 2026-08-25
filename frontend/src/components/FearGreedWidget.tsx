/** Free "Fear & Greed" gauge computed server-side from index momentum,
 *  RSI strength and volatility — no external paid API. */
import { motion } from 'framer-motion';
import { useMarketStore } from '../store/marketStore';
import { EmptyState, ErrorState, LoadingSpinner } from './States';

function gaugeColor(score: number): string {
  return score < 25 ? '#ef4444' : score < 45 ? '#f97316'
    : score < 56 ? '#eab308' : score < 76 ? '#22c55e' : '#10b981';
}

export default function FearGreedWidget() {
  const { data, loading, error } = useMarketStore((s) => s.fearGreed);
  const updatedAt = useMarketStore((s) => s.fearGreedUpdatedAt);
  const fetchAll = useMarketStore((s) => s.fetchAll);

  // Semicircle gauge geometry: r=60 centered at (80, 80), angle -180..0.
  const score = data?.score ?? 50;
  const needleAngle = -180 + (score / 100) * 180;
  const radians = (needleAngle * Math.PI) / 180;
  const nx = 80 + 52 * Math.cos(radians);
  const ny = 80 + 52 * Math.sin(radians);

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60
      p-4 text-center" data-testid="fear-greed">
      <h2 className="mb-2 text-sm font-semibold text-slate-300">
        Fear &amp; Greed Index</h2>
      {updatedAt !== null && (
        <p className="-mt-1 mb-2 text-[9px] uppercase tracking-widest
          text-slate-600">
          Auto-refreshes every 90s{updatedAt
            ? ` · ${Math.max(0, Math.round((Date.now() - updatedAt) / 1000))}s ago`
            : ''}</p>
      )}
      {loading && <LoadingSpinner label="" />}
      {error && <ErrorState message={error} onRetry={() => void fetchAll()} />}
      {!loading && !error && !data && (
        <EmptyState message="Awaiting index history." />
      )}
      {!loading && !error && data && (
        <>
          <svg viewBox="0 0 160 92" className="mx-auto w-44">
            <path d="M 20 80 A 60 60 0 0 1 140 80" fill="none"
              stroke="#1e293b" strokeWidth="12" strokeLinecap="round" />
            <motion.path d="M 20 80 A 60 60 0 0 1 140 80" fill="none"
              stroke={gaugeColor(score)} strokeWidth="12"
              strokeLinecap="round"
              initial={{ pathLength: 0 }}
              animate={{ pathLength: score / 100 }}
              transition={{ duration: 1 }} />
            <line x1={80} y1={80}
              x2={Number.isFinite(nx) ? nx : 28}
              y2={Number.isFinite(ny) ? ny : 80}
              stroke="#e2e8f0" strokeWidth="2.5" strokeLinecap="round" />
            <circle cx={80} cy={80} r={4} fill="#e2e8f0" />
          </svg>
          <p className="mt-1 text-2xl font-bold"
            style={{ color: gaugeColor(score) }}>{data.score}</p>
          <p className="text-xs uppercase tracking-widest text-slate-400">
            {data.label}</p>
          <dl className="mt-3 space-y-1 text-left">
            {Object.entries(data.components).map(([key, value]) => (
              <div key={key} className="flex justify-between text-[10px]
                text-slate-500">
                <dt>{key.replace(/_/g, ' ')}</dt>
                <dd className="text-slate-400">{value.toFixed(0)}</dd>
              </div>
            ))}
          </dl>
        </>
      )}
    </section>
  );
}
