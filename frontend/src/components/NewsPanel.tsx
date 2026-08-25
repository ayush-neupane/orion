/** Real-time news aggregator panel with per-headline sentiment badges.
 *  Freshness policy mirrors the backend: ≤72h normally, hard cap 7 days. */
import { useMarketStore } from '../store/marketStore';
import { EmptyState, ErrorState, LoadingSpinner } from './States';

const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const minutes = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function SentimentBadge({ label }: { label: 'BULLISH' | 'BEARISH' | 'NEUTRAL' }) {
  const style = label === 'BULLISH'
    ? 'bg-emerald-500/15 text-emerald-400'
    : label === 'BEARISH'
      ? 'bg-rose-500/15 text-rose-400'
      : 'bg-slate-600/30 text-slate-400';
  return (
    <span className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${style}`}>
      {label}
    </span>
  );
}

export default function NewsPanel() {
  const { data, loading, error } = useMarketStore((s) => s.news);
  const region = useMarketStore((s) => s.region);
  const fetchAll = useMarketStore((s) => s.fetchAll);

  // Defensive client-side freshness filter (backend already enforces this).
  const items = (data ?? []).filter((item) => {
    const then = new Date(item.published_at).getTime();
    return !Number.isNaN(then)
      && then <= Date.now()
      && Date.now() - then <= MAX_AGE_MS;
  });

  return (
    <section id="news" className="flex h-full flex-col rounded-xl border border-slate-800
      bg-slate-900/60 p-4" data-testid="news-panel">
      <header className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-300">News Aggregator
          <span className="ml-2 rounded bg-slate-800 px-1.5 py-0.5
            text-[10px] text-sky-400">{region}</span></h2>
        <span className="flex items-center gap-1 rounded bg-emerald-500/10
          px-1.5 py-0.5 text-[9px] font-bold tracking-wider
          text-emerald-400" title="Only headlines from the last 72 hours
          are shown (max 7 days)">
          <span className="h-1 w-1 animate-pulse rounded-full
            bg-emerald-400" aria-hidden />
          FRESH
        </span>
      </header>
      {loading && <LoadingSpinner label="Fetching headlines…" />}
      {error && <ErrorState message={error} onRetry={() => void fetchAll()} />}
      {!loading && !error && items.length === 0 && (
        <EmptyState message="No recent headlines right now — only stories
          from the last 72 hours are served (7-day max). The news worker
          refreshes every 30 minutes." />
      )}
      {!loading && !error && items.length > 0 && (
        <ul className="slim-scroll max-h-[560px] space-y-3 overflow-y-auto
          pr-1">
          {items.map((item) => {
            const ageMin = Math.max(0,
              (Date.now() - new Date(item.published_at).getTime()) / 60000);
            return (
              <li key={item.url} className="border-b border-slate-800/60 pb-3">
                <a href={item.url} target="_blank"
                  rel="noopener noreferrer nofollow"
                  className="text-xs font-medium leading-snug text-slate-200
                    transition-colors hover:text-sky-400">
                  {ageMin < 60 && (
                    <span className="mr-1.5 inline-block h-1.5 w-1.5
                      animate-pulse rounded-full bg-sky-400 align-middle"
                      aria-label="new" />
                  )}
                  {item.title}
                </a>
                <div className="mt-1 flex items-center gap-2 text-[10px]
                  text-slate-500">
                  <span>{item.source}</span>
                  <span>·</span>
                  <span>{timeAgo(item.published_at)}</span>
                  <SentimentBadge label={item.sentiment_label} />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
