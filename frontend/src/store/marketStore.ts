/**
 * Zustand store: region selection, quotes, movers, predictions, underdogs,
 * news, Fear & Greed, chart history and auth state. Every slice tracks its
 * own loading/error flags so components can render all three states.
 */
import { create } from 'zustand';
import { z } from 'zod';
import {
  apiGet, apiPost, setToken, getToken, ApiError,
} from '../api/client';
import {
  FearGreedSchema, HistoryPointSchema, MoversSchema, NewsItemSchema,
  PredictionSchema, SearchHitSchema, TokenPairSchema, UserOutSchema,
  type FearGreed, type HistoryPoint, type Movers, type NewsItem,
  type OrionUser, type Prediction, type Quote, type SearchHit,
} from '../types/market';

export const REGIONS = ['GLOBAL', 'US', 'UK', 'EU', 'JP', 'IN'] as const;
export type Region = (typeof REGIONS)[number];

export interface LiveTick { symbol: string; price: number }

interface SliceState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

const idle = <T,>(): SliceState<T> => ({
  data: null, loading: false, error: null });

const arraySchema = <T>(inner: z.ZodType<T>): z.ZodType<T[]> =>
  z.array(inner) as unknown as z.ZodType<T[]>;

const barsSchema =
  z.object({ bars: z.array(HistoryPointSchema), simulated: z.boolean() }) as
  unknown as z.ZodType<{ bars: HistoryPoint[]; simulated: boolean }>;

async function loadSlice<T>(
  set: (partial: Partial<MarketState>) => void,
  key: 'movers' | 'predictions' | 'underdogs' | 'news' | 'fearGreed'
    | 'history',
  path: string,
  schema: { parse: (v: unknown) => T },
): Promise<void> {
  set({ [key]: { ...idle<T>(), loading: true } } as Partial<MarketState>);
  try {
    const data = await apiGet(path, schema);
    if (key === 'history') {
      const payload = data as unknown as {
        bars?: HistoryPoint[]; simulated?: boolean };
      set({
        history: { data: payload.bars ?? [], loading: false, error: null },
        historySimulated: Boolean(payload.simulated),
      } as Partial<MarketState>);
    } else {
      const patch: Record<string, unknown> = {
        [key]: { data, loading: false, error: null },
      };
      if (key === 'fearGreed') patch.fearGreedUpdatedAt = Date.now();
      set(patch as Partial<MarketState>);
    }
  } catch (err) {
    const message = err instanceof ApiError
      ? err.message : 'An internal error occurred';
    set({
      [key]: { data: null, loading: false, error: message },
    } as Partial<MarketState>);
  }
}

interface MarketState {
  region: Region;
  setRegion: (region: Region) => void;

  quotes: SliceState<Quote[]>;
  movers: SliceState<Movers>;
  predictions: SliceState<Prediction[]>;
  underdogs: SliceState<Prediction[]>;
  news: SliceState<NewsItem[]>;
  fearGreed: SliceState<FearGreed>;
  history: SliceState<HistoryPoint[]>;
  historySimulated: boolean;
  /** Latest WS tick — drives real-time candle updates in the chart. */
  lastTick: LiveTick | null;
  /** Epoch ms of the last successful Fear & Greed fetch. */
  fearGreedUpdatedAt: number | null;

  selectedSymbol: string | null;
  selectSymbol: (symbol: string | null) => void;

  searchResults: SearchHit[];
  search: (q: string) => Promise<void>;

  user: OrionUser | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, username: string,
    password: string) => Promise<void>;
  logout: () => void;
  bootstrapUser: () => Promise<void>;

  fetchAll: () => Promise<void>;
  fetchHistory: (symbol: string) => Promise<void>;
}

export const useMarketStore = create<MarketState>((set, get) => ({
  region: 'GLOBAL',
  setRegion: (region) => {
    set({ region });
    void get().fetchAll();
  },

  quotes: idle(),
  movers: idle(),
  predictions: idle(),
  underdogs: idle(),
  news: idle(),
  fearGreed: idle(),
  history: idle(),
  historySimulated: false,
  lastTick: null,
  fearGreedUpdatedAt: null,

  selectedSymbol: null,
  selectSymbol: (symbol) => {
    set({ selectedSymbol: symbol });
    if (symbol) void get().fetchHistory(symbol);
  },

  searchResults: [],
  search: async (q) => {
    if (!q.trim()) {
      set({ searchResults: [] });
      return;
    }
    try {
      const hits = await apiGet(
        `/market/search?q=${encodeURIComponent(q.trim())}`,
        arraySchema(SearchHitSchema));
      set({ searchResults: hits });
    } catch {
      set({ searchResults: [] });
    }
  },

  user: null,
  login: async (email, password) => {
    const pair = await apiPost('/auth/login', { email, password },
      TokenPairSchema, { withCredentials: true });
    setToken(pair.access_token);
    await get().bootstrapUser();
  },
  register: async (email, username, password) => {
    const pair = await apiPost('/auth/register',
      { email, username, password },
      TokenPairSchema, { withCredentials: true });
    setToken(pair.access_token);
    await get().bootstrapUser();
  },
  logout: () => {
    apiPost('/auth/logout', {}, UserOutSchema, { withCredentials: true })
      .catch(() => undefined)
      .finally(() => {
        setToken(null);
        set({ user: null });
      });
  },
  bootstrapUser: async () => {
    if (!getToken()) return;
    try {
      const me = await apiGet('/auth/me', UserOutSchema);
      set({ user: me });
    } catch {
      set({ user: null });
    }
  },

  fetchAll: async () => {
    const region = get().region;
    await Promise.all([
      loadSlice(set, 'movers', `/market/movers?region=${region}`,
        MoversSchema),
      loadSlice(set, 'predictions', `/market/predictions?region=${region}`,
        arraySchema(PredictionSchema)),
      loadSlice(set, 'underdogs', `/market/underdogs?region=${region}`,
        arraySchema(PredictionSchema)),
      loadSlice(set, 'news', `/news?region=${region}&limit=25`,
        arraySchema(NewsItemSchema)),
      loadSlice(set, 'fearGreed', '/market/fear-greed', FearGreedSchema),
    ]);
    if (!get().selectedSymbol) {
      const moversData = get().movers.data;
      const first = moversData?.gainers[0] ?? moversData?.most_active[0];
      if (first) get().selectSymbol(first.symbol);
    }
  },

  fetchHistory: async (symbol) => {
    const region = get().region === 'GLOBAL' ? 'US' : get().region;
    await loadSlice(set, 'history',
      `/market/history/${encodeURIComponent(symbol)}?region=${region}`,
      barsSchema);
  },
}));

