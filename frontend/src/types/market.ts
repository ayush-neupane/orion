/**
 * Runtime validation of every API response via zod.
 * A malformed or hostile payload can never reach the UI unchecked.
 */
import { z } from 'zod';

export const EnvelopeSchema = z.object({
  status: z.enum(['success', 'fail']),
  data: z.unknown().optional(),
  message: z.string().nullish(),
  timestamp: z.string(),
});

export const QuoteSchema = z.object({
  symbol: z.string(),
  name: z.string().default(''),
  price: z.number(),
  change: z.number().default(0),
  change_percent: z.number().default(0),
  volume: z.number().default(0),
  simulated: z.boolean().default(false),
});
export type Quote = z.infer<typeof QuoteSchema>;

export const MoversSchema = z.object({
  gainers: z.array(QuoteSchema).default([]),
  losers: z.array(QuoteSchema).default([]),
  most_active: z.array(QuoteSchema).default([]),
});
export type Movers = z.infer<typeof MoversSchema>;

export const HistoryPointSchema = z.object({
  time: z.string(),
  open: z.number(),
  high: z.number(),
  low: z.number(),
  close: z.number(),
  volume: z.number().default(0),
});
export type HistoryPoint = z.infer<typeof HistoryPointSchema>;

export const PredictionSchema = z.object({
  symbol: z.string(),
  region: z.string(),
  prob_up: z.number(),
  recommendation: z.enum(['BUY', 'HOLD', 'SELL']),
  breakout_score: z.number().int(),
  pe_ratio: z.number().nullable().optional(),
  volume_trend_3d: z.number().default(0),
  sentiment_score: z.number().default(0),
});
export type Prediction = z.infer<typeof PredictionSchema>;

export const NewsItemSchema = z.object({
  url: z.string().url(),
  title: z.string(),
  source: z.string(),
  region: z.string().default('GLOBAL'),
  sentiment_label: z.enum(['BULLISH', 'BEARISH', 'NEUTRAL']),
  sentiment_score: z.number(),
  published_at: z.string(),
});
export type NewsItem = z.infer<typeof NewsItemSchema>;

export const FearGreedSchema = z.object({
  score: z.number().int().min(0).max(100),
  label: z.string(),
  components: z.record(z.number()).default({}),
});
export type FearGreed = z.infer<typeof FearGreedSchema>;

export const SearchHitSchema = z.object({
  symbol: z.string(),
  name: z.string(),
  region: z.string(),
});
export type SearchHit = z.infer<typeof SearchHitSchema>;

export const RegionsSchema = z.object({
  regions: z.array(z.string()),
  indices: z.record(z.object({ symbol: z.string(), name: z.string() })),
});

export const TokenPairSchema = z.object({
  access_token: z.string(),
  token_type: z.string().default('bearer'),
  expires_in: z.number(),
});

export const UserOutSchema = z.object({
  id: z.number(),
  email: z.string(),
  username: z.string(),
  created_at: z.string(),
});
export type OrionUser = z.infer<typeof UserOutSchema>;
