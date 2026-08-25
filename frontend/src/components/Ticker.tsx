/** Scrolling live market ticker with green/red colour coding. */
import { useMarketStore } from '../store/marketStore';
import { Quote } from '../types/market';
import { EmptyState, LoadingSpinner } from './States';

function TickerItem({ quote }: { quote: Quote }) {
  const up = quote.change_percent >= 0;
  return (
    <button
      className="mx-6 inline-flex items-baseline gap-2 rounded-md px-2 py-0.5
        text-sm transition-colors hover:bg-slate-800/70"
      onClick={() => useMarketStore.getState().selectSymbol(quote.symbol)}
      data-testid={`ticker-${quote.symbol}`}>
      <span className="font-semibold text-slate-200">{quote.symbol}</span>
      <span className="text-slate-400 tabular-nums">
        {quote.price.toLocaleString(undefined,
          { maximumFractionDigits: 2 })}
      </span>
      <span className={`tabular-nums ${up
        ? 'text-emerald-400' : 'text-rose-400'}`}>
        {up ? '▲' : '▼'} {Math.abs(quote.change_percent).toFixed(2)}%
      </span>
    </button>
  );
}

export default function Ticker() {
  const movers = useMarketStore((s) => s.movers);
  const quotes = movers.data
    ? [...movers.data.gainers, ...movers.data.losers,
       ...movers.data.most_active]
        .filter((q, i, arr) => arr.findIndex(
          (x) => x.symbol === q.symbol) === i)
    : null;

  return (
    <div className="overflow-hidden border-y border-slate-800 bg-slate-900/80
      py-2" data-testid="ticker">
      {movers.loading && quotes === null && (
        <div className="px-4"><LoadingSpinner label="Loading ticker…" /></div>
      )}
      {quotes && quotes.length === 0 && (
        <EmptyState message="Ticker unavailable for this market yet." />
      )}
      {quotes && quotes.length > 0 && (
        <div className="ticker-track">
          {[0, 1].map((copy) => (
            <span key={copy} aria-hidden={copy === 1}>
              {quotes.map((q) => <TickerItem key={`${copy}-${q.symbol}`}
                quote={q} />)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
