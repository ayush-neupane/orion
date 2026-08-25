/** Main dashboard: globe, ticker, movers, underdogs, predictions,
 *  chart, Fear & Greed gauge and news — with live WS ticks. */
import { useEffect } from 'react';
import Header from '../components/Header';
import Globe from '../components/Globe';
import Chart from '../components/Chart';
import Ticker from '../components/Ticker';
import TopMovers from '../components/TopMovers';
import UnderdogScanner from '../components/UnderdogScanner';
import PredictionsTable from '../components/PredictionsTable';
import NewsPanel from '../components/NewsPanel';
import FearGreedWidget from '../components/FearGreedWidget';
import RegionClock from '../components/RegionClock';
import { useMarketStore } from '../store/marketStore';

/** Keeps a live WebSocket connection open so the dashboard receives
 *  real-time tick broadcasts. Market data is public: the connection is
 *  anonymous (guest) unless an access token is available. */
function useLiveTicks() {
  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    let socket: WebSocket | null = null;
    let disposed = false;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let attempts = 0;

    const connect = () => {
      if (disposed) return;
      const token = localStorage.getItem('orion.access');
      const authQuery = token ? `?token=${encodeURIComponent(token)}` : '';
      try {
        socket = new WebSocket(
          `${proto}://${window.location.host}/ws/market${authQuery}`);
      } catch {
        scheduleReconnect();
        return;
      }
      socket.onopen = () => {
        attempts = 0;
        socket?.send(JSON.stringify({ subscribe: 'GLOBAL' }));
      };
      socket.onmessage = (event) => {
        try {
          const tick = JSON.parse(String(event.data)) as {
            event?: string; symbol?: string; price?: number };
          if (tick.event === 'tick' && tick.symbol
            && typeof tick.price === 'number') {
            // Feed the chart's real-time candle layer.
            useMarketStore.setState({
              lastTick: { symbol: tick.symbol, price: tick.price },
            });
            // Nudge matching quote prices so the ticker stays live between
            // REST polls.
            useMarketStore.setState((state) => {
              if (!state.movers.data) return state;
              const patch = (list: typeof state.movers.data.gainers) =>
                list.map((q) => q.symbol === tick.symbol
                  ? { ...q, price: tick.price as number } : q);
              return {
                movers: {
                  ...state.movers,
                  data: {
                    gainers: patch(state.movers.data.gainers),
                    losers: patch(state.movers.data.losers),
                    most_active: patch(state.movers.data.most_active),
                  },
                },
              };
            });
          }
        } catch {
          /* malformed frame - ignore */
        }
      };
      socket.onclose = () => {
        // Auto-reconnect with capped backoff so ticks survive backend
        // restarts and transient network drops without a page reload.
        if (!disposed) scheduleReconnect();
      };
    };

    const scheduleReconnect = () => {
      if (disposed || retry) return;
      attempts += 1;
      const delay = Math.min(2_000 * attempts, 15_000);
      retry = setTimeout(() => {
        retry = null;
        connect();
      }, delay);
    };

    connect();
    return () => {
      disposed = true;
      if (retry) clearTimeout(retry);
      socket?.close();
    };
  }, []);
  return null;
}

export default function Dashboard() {
  const fetchAll = useMarketStore((s) => s.fetchAll);
  useLiveTicks();

  useEffect(() => {
    void fetchAll();
    const interval = setInterval(() => { void fetchAll(); },
      90_000); // periodic refresh; WS keeps it feeling live between polls
    return () => clearInterval(interval);
  }, [fetchAll]);

  return (
    <div id="top" className="min-h-screen bg-slate-950" data-testid="dashboard">
      <Header />
      <Ticker />
      <main className="mx-auto grid max-w-[1600px] gap-4 p-4
        lg:grid-cols-[1fr_340px]">
        {/* Left column */}
        <div className="space-y-4">
          <div className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
            <div className="grid content-start gap-4">
              <Globe />
              <RegionClock />
            </div>
            <div className="grid gap-4">
              <Chart />
              <FearGreedWidget />
            </div>
          </div>
          <TopMovers />
          <UnderdogScanner />
          <PredictionsTable />
        </div>
        {/* Right column */}
        <aside className="lg:sticky lg:top-20 lg:h-[calc(100vh-6rem)]">
          <NewsPanel />
        </aside>
      </main>
      <footer className="border-t border-slate-800/80 bg-slate-950 px-4
        py-5 text-center text-[10px] leading-relaxed text-slate-600">
        <nav aria-label="Dashboard sections" className="mb-2 flex flex-wrap
          items-center justify-center gap-x-4 gap-y-1">
          <a className="transition-colors hover:text-sky-400"
            href="#top">Overview</a>
          <a className="transition-colors hover:text-sky-400"
            href="#chart">Chart</a>
          <a className="transition-colors hover:text-sky-400"
            href="#movers">Top Movers</a>
          <a className="transition-colors hover:text-sky-400"
            href="#underdogs">Underdogs</a>
          <a className="transition-colors hover:text-sky-400"
            href="#predictions">Predictions</a>
          <a className="transition-colors hover:text-sky-400"
            href="#news">News</a>
        </nav>
        <p>
          ORION · Open-source market intelligence · Data: free public
          sources · Not investment advice.
        </p>
        <p className="mt-1 text-slate-700">
          Quotes refresh continuously over WebSocket · News window:
          last 72 hours (max 7 days)
        </p>
      </footer>
    </div>
  );
}
