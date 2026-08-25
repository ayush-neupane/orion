/** Top 10 Gainers / Losers / Most Active for the selected market. */
import { useMarketStore } from '../store/marketStore';
import { Quote } from '../types/market';
import { EmptyState, ErrorState, LoadingSpinner } from './States';

function QuoteRow({ quote }: { quote: Quote }) {
  const up = quote.change_percent >= 0;
  return (
    <button className="flex w-full items-center justify-between rounded px-2
      py-1.5 text-xs hover:bg-slate-800/60 transition-colors"
      onClick={() => useMarketStore.getState().selectSymbol(quote.symbol)}>
      <span className="font-medium text-slate-200">{quote.symbol}</span>
      <span className="flex items-center gap-2">
        <span className="text-slate-400">{quote.price.toFixed(2)}</span>
        <span className={up ? 'text-emerald-400' : 'text-rose-400'}>
          {up ? '+' : ''}{quote.change_percent.toFixed(2)}%
        </span>
      </span>
    </button>
  );
}

function MoverColumn({ title, quotes, accent }: {
  title: string; quotes: Quote[] | undefined; accent: string }) {
  return (
    <div className="flex-1" data-testid={`movers-${title}`}>
      <h3 className={`mb-2 text-xs font-semibold uppercase tracking-wider
        ${accent}`}>{title}</h3>
      {!quotes && <p className="text-xs text-slate-600">—</p>}
      {quotes?.length === 0 && (
        <p className="text-xs text-slate-600">No data yet</p>
      )}
      <div className="space-y-0.5">
        {quotes?.slice(0, 10).map((q) => <QuoteRow key={q.symbol}
          quote={q} />)}
      </div>
    </div>
  );
}

export default function TopMovers() {
  const { data, loading, error } = useMarketStore((s) => s.movers);
  const region = useMarketStore((s) => s.region);
  const fetchAll = useMarketStore((s) => s.fetchAll);

  return (
    <section id="movers" className="rounded-xl border border-slate-800 bg-slate-900/60
      p-4" data-testid="top-movers">
      <header className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-300">Top Movers
          <span className="ml-2 rounded bg-slate-800 px-1.5 py-0.5
            text-[10px] text-sky-400">{region}</span></h2>
      </header>
      {loading && <LoadingSpinner />}
      {error && <ErrorState message={error} onRetry={() => void fetchAll()} />}
      {!loading && !error && data && (
        <div className="flex gap-6">
          <MoverColumn title="Gainers" quotes={data.gainers}
            accent="text-emerald-400" />
          <MoverColumn title="Losers" quotes={data.losers}
            accent="text-rose-400" />
          <MoverColumn title="Most Active" quotes={data.most_active}
            accent="text-sky-400" />
        </div>
      )}
      {!loading && !error && !data && (
        <EmptyState message="Movers data will appear after the next
          ingestion cycle." />
      )}
    </section>
  );
}
