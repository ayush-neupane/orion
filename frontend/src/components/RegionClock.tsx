/**
 * Live market clocks for the selected region.
 * - Ticks every second, pure client-side via Intl.DateTimeFormat
 *   (zero dependencies, zero network calls).
 * - A specific region shows that exchange's local time; GLOBAL shows
 *   every exchange. Each clock carries a live OPEN/CLOSED session badge.
 */
import { useEffect, useState } from 'react';
import { useMarketStore, type Region } from '../store/marketStore';

interface MarketClock {
  region: Exclude<Region, 'GLOBAL'>;
  city: string;
  flag: string;
  tz: string;
  /** Regular session bounds in local minutes since midnight. */
  open: number;
  close: number;
}

const MARKETS: MarketClock[] = [
  { region: 'US', city: 'New York', flag: '🇺🇸', tz: 'America/New_York',
    open: 9 * 60 + 30, close: 16 * 60 },
  { region: 'UK', city: 'London', flag: '🇬🇧', tz: 'Europe/London',
    open: 8 * 60, close: 16 * 60 + 30 },
  { region: 'EU', city: 'Frankfurt', flag: '🇪🇺', tz: 'Europe/Berlin',
    open: 9 * 60, close: 17 * 60 + 30 },
  { region: 'JP', city: 'Tokyo', flag: '🇯🇵', tz: 'Asia/Tokyo',
    open: 9 * 60, close: 15 * 60 },
  { region: 'IN', city: 'Mumbai', flag: '🇮🇳', tz: 'Asia/Kolkata',
    open: 9 * 60 + 15, close: 15 * 60 + 30 },
];

/** Shared 1-second heartbeat so all clocks tick together. */
function useNow(ms = 1000): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), ms);
    return () => clearInterval(id);
  }, [ms]);
  return now;
}

function localParts(tz: string, now: Date) {
  const time = new Intl.DateTimeFormat('en-GB', {
    timeZone: tz, hour: '2-digit', minute: '2-digit', second: '2-digit',
    hourCycle: 'h23',
  }).format(now);
  const weekday = new Intl.DateTimeFormat('en-US', {
    timeZone: tz, weekday: 'short',
  }).format(now);
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: tz, hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(now);
  const hour = Number(parts.find((p) => p.type === 'hour')?.value ?? 0) % 24;
  const minute = Number(parts.find((p) => p.type === 'minute')?.value ?? 0);
  const minutes = hour * 60 + minute;
  const isWeekend = weekday === 'Sat' || weekday === 'Sun';
  return { time, weekday, minutes, isWeekend };
}

function ClockCard({ market, now }: { market: MarketClock; now: Date }) {
  const { time, weekday, minutes, isWeekend } =
    localParts(market.tz, now);
  const isOpen = !isWeekend && minutes >= market.open && minutes < market.close;
  return (
    <div className="rounded-lg border border-slate-800/80 bg-slate-950/60
      px-3 py-2" data-testid={`clock-${market.region.toLowerCase()}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-medium text-slate-400">
          {market.flag} {market.city}
        </span>
        <span className={`flex items-center gap-1 rounded px-1.5 py-0.5
          text-[9px] font-bold tracking-wider ${isOpen
            ? 'bg-emerald-500/10 text-emerald-400'
            : 'bg-slate-800/60 text-slate-500'}`}>
          <span className={`h-1 w-1 rounded-full ${isOpen
            ? 'animate-pulse bg-emerald-400'
            : 'bg-slate-600'}`} aria-hidden />
          {isOpen ? 'OPEN' : 'CLOSED'}
        </span>
      </div>
      <p className="mt-1 font-mono text-xl tabular-nums text-slate-100">
        {time}
      </p>
      <p className="text-[10px] text-slate-500">
        {weekday} · {market.region} local
      </p>
    </div>
  );
}

export default function RegionClock() {
  const region = useMarketStore((s) => s.region);
  const now = useNow();
  const visible = region === 'GLOBAL'
    ? MARKETS
    : MARKETS.filter((m) => m.region === region);

  return (
    <section aria-label="Market clocks"
      className="rounded-xl border border-slate-800 bg-slate-900/60 p-4"
      data-testid="region-clocks">
      <header className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold tracking-wide text-slate-300">
          Market Clocks
        </h2>
        <span className="rounded bg-sky-500/15 px-1.5 py-0.5 text-[9px]
          font-bold tracking-wider text-sky-400">
          {region}
        </span>
      </header>
      <div className={visible.length > 1
        ? 'grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-3'
        : 'grid grid-cols-1 gap-2'}>
        {visible.map((m) => (
          <ClockCard key={m.region} market={m} now={now} />
        ))}
      </div>
    </section>
  );
}
