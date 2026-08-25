/**
 * Typed API client: envelope validation, bearer auth, single silent
 * token-refresh retry on 401. All responses are zod-validated.
 */
import { EnvelopeSchema } from '../types/market';

const BASE = import.meta.env.VITE_API_BASE ?? '/api';
const TOKEN_KEY = 'orion.access';

export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

async function parseEnvelope(response: Response): Promise<{
  status: string;
  data?: unknown;
  message?: string | null;
}> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ApiError('An internal error occurred', response.status);
  }
  const parsed = EnvelopeSchema.safeParse(body);
  if (!parsed.success) {
    throw new ApiError('An internal error occurred', response.status);
  }
  return parsed.data as { status: string; data?: unknown; message?: string | null };
}

async function rawRequest<T>(
  path: string,
  options: RequestInit,
  schema: { parse: (v: unknown) => T },
  allowRefresh: boolean,
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set('Content-Type', 'application/json');
  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const response = await fetch(`${BASE}${path}`, { ...options, headers });

  if (response.status === 401 && allowRefresh && getToken()) {
    const refreshed = await fetch(`${BASE}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    });
    if (refreshed.ok) {
      const refreshedBody = await parseEnvelope(refreshed);
      if (refreshedBody.status === 'success' && refreshedBody.data) {
        setToken(
          (refreshedBody.data as { access_token: string }).access_token,
        );
        return rawRequest(path, options, schema, false);
      }
    }
    setToken(null);
  }

  const envelope = await parseEnvelope(response);
  if (!response.ok || envelope.status !== 'success') {
    throw new ApiError(envelope.message || 'An internal error occurred',
      response.status);
  }
  return schema.parse(envelope.data);
}

export async function apiGet<T>(
  path: string,
  schema: { parse: (v: unknown) => T },
): Promise<T> {
  return rawRequest(path, { method: 'GET' }, schema, true);
}

export async function apiPost<T>(
  path: string,
  payload: unknown,
  schema: { parse: (v: unknown) => T },
  opts: { withCredentials?: boolean } = {},
): Promise<T> {
  return rawRequest(
    path,
    {
      method: 'POST',
      body: JSON.stringify(payload),
      credentials: opts.withCredentials ? 'include' : undefined,
    },
    schema,
    !opts.withCredentials,
  );
}

export async function apiDelete<T>(
  path: string,
  schema: { parse: (v: unknown) => T },
): Promise<T> {
  return rawRequest(path, { method: 'DELETE' }, schema, true);
}
