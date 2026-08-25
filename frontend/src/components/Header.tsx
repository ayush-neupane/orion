/** Header: brand, region pills (synced with globe clicks), debounced
 *  symbol search with dropdown, and auth controls. */
import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { useMarketStore, REGIONS } from '../store/marketStore';

const REGION_FLAGS: Record<string, string> = {
  GLOBAL: '🌐', US: '🇺🇸', UK: '🇬🇧', EU: '🇪🇺', JP: '🇯🇵', IN: '🇮🇳',
};

export function RegionPills() {
  const region = useMarketStore((s) => s.region);
  const setRegion = useMarketStore((s) => s.setRegion);
  return (
    <div className="flex flex-wrap items-center gap-1 rounded-lg border
      border-slate-800 bg-slate-900/70 p-1" role="tablist"
      aria-label="Market regions" data-testid="region-pills">
      {REGIONS.map((r) => (
        <button key={r} role="tab" aria-selected={region === r}
          onClick={() => setRegion(r)}
          className={`rounded-md px-2.5 py-1 text-[11px] font-semibold
            transition-all duration-200 ${region === r
              ? 'bg-sky-500/20 text-sky-300 shadow-sm shadow-sky-500/20'
              : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'}`}
          data-testid={`region-${r}`}>
          <span aria-hidden className="mr-1">{REGION_FLAGS[r]}</span>{r}
        </button>
      ))}
    </div>
  );
}

function SearchBar() {
  const search = useMarketStore((s) => s.search);
  const results = useMarketStore((s) => s.searchResults);
  const selectSymbol = useMarketStore((s) => s.selectSymbol);
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  const onChange = (value: string) => {
    setQuery(value);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      await search(value);
      setOpen(value.trim().length > 0);
    }, 300);
  };

  return (
    <div className="relative w-64">
      <input
        type="search"
        value={query}
        placeholder="Search markets… e.g. NVDA"
        aria-label="Search symbols"
        className="w-full rounded-md border border-slate-700 bg-slate-900
          px-3 py-1.5 text-xs text-slate-200 placeholder-slate-600
          focus:border-sky-500 focus:outline-none"
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setOpen(query.trim().length > 0)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        data-testid="symbol-search"
      />
      {open && results.length > 0 && (
        <ul className="absolute z-30 mt-1 w-full overflow-hidden rounded-md
          border border-slate-700 bg-slate-900 shadow-xl">
          {results.map((hit) => (
            <li key={`${hit.region}-${hit.symbol}`}>
              <button className="flex w-full items-center justify-between
                px-3 py-1.5 text-xs hover:bg-slate-800"
                onMouseDown={() => {
                  selectSymbol(hit.symbol);
                  setQuery(hit.symbol);
                  setOpen(false);
                }}>
                <span className="font-semibold text-slate-200">
                  {hit.symbol}</span>
                <span className="text-slate-500">{hit.name} · {hit.region}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function AuthModal({ onClose }: { onClose: () => void }) {
  const login = useMarketStore((s) => s.login);
  const register = useMarketStore((s) => s.register);
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Escape-to-close and background scroll lock while the dialog is open.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose]);

  const submit = async () => {
    setError(null);
    setBusy(true);
    try {
      if (mode === 'login') await login(email, password);
      else await register(email, username, password);
      onClose();
    } catch (err) {
      setError(err instanceof Error
        ? err.message : 'An internal error occurred');
    } finally {
      setBusy(false);
    }
  };

  const fieldClass = 'w-full rounded-lg border border-slate-700 bg-slate-950/80 ' +
    'px-3 py-2 text-xs text-slate-200 placeholder-slate-600 transition-colors ' +
    'focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500/40';

  // Render through a portal to <body>: ancestors with backdrop-filter
  // (the glassy header) become containing blocks for position:fixed and
  // would otherwise clip the dialog to the header box instead of the
  // viewport. The portal guarantees true full-screen centering.
  return createPortal(
    <motion.div
      className="fixed inset-0 z-[100] flex items-center justify-center
        bg-slate-950/70 p-4 backdrop-blur-sm"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      exit={{ opacity: 0 }} transition={{ duration: 0.15 }}
      onClick={onClose} data-testid="auth-modal">
      <motion.div role="dialog" aria-modal="true" aria-label={mode === 'login'
        ? 'Sign in to ORION' : 'Create ORION account'}
        className="w-full max-w-sm overflow-hidden rounded-2xl border
          border-slate-700/80 bg-slate-900 shadow-2xl shadow-black/60"
        initial={{ opacity: 0, scale: 0.95, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 8 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        onClick={(e) => e.stopPropagation()}>
        <div className="h-0.5 w-full bg-gradient-to-r from-transparent
          via-sky-500 to-transparent" />
        <div className="p-6 pt-5">
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-sm font-bold text-slate-100">
                {mode === 'login' ? 'Welcome back' : 'Create your account'}
              </h2>
              <p className="mt-0.5 text-[11px] text-slate-500">
                {mode === 'login'
                  ? 'Sign in to your ORION workspace'
                  : 'Join ORION — free, forever'}</p>
            </div>
            <button onClick={onClose} aria-label="Close dialog"
              data-testid="auth-close"
              className="rounded-md p-1 text-slate-500 transition-colors
                hover:bg-slate-800 hover:text-slate-200">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none"
                aria-hidden>
                <path d="M1 1l12 12M13 1L1 13" stroke="currentColor"
                  strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            </button>
          </div>
          <form className="space-y-3" onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}>
            <input type="email" required placeholder="Email" value={email}
              autoFocus onChange={(e) => setEmail(e.target.value)}
              className={fieldClass} autoComplete="email" />
            {mode === 'register' && (
              <input required minLength={3} maxLength={32}
                placeholder="Username" value={username}
                onChange={(e) => setUsername(e.target.value)}
                className={fieldClass} autoComplete="username" />
            )}
            <input type="password" required minLength={10} maxLength={128}
              placeholder="Password (10+ chars, 1 uppercase, 1 digit)"
              value={password} onChange={(e) => setPassword(e.target.value)}
              className={fieldClass}
              autoComplete={mode === 'login' ? 'current-password'
                : 'new-password'} />
            {error && (
              <p className="rounded-md border border-rose-500/20 bg-rose-500/10
                px-3 py-2 text-xs text-rose-400" role="alert">{error}</p>
            )}
            <button type="submit" disabled={busy}
              className="w-full rounded-lg bg-gradient-to-r from-sky-500 to-cyan-400
                py-2 text-xs font-bold text-slate-950 shadow-lg shadow-sky-500/25
                hover:from-sky-400 hover:to-cyan-300 disabled:opacity-50
                disabled:shadow-none transition-all">
              {busy ? 'Working…'
                : mode === 'login' ? 'Sign in securely' : 'Create account'}
            </button>
          </form>
          <button className="mt-4 w-full text-center text-[11px]
            text-slate-500 transition-colors hover:text-sky-400"
            onClick={() => {
              setMode(mode === 'login' ? 'register' : 'login');
              setError(null);
            }}>
            {mode === 'login'
              ? 'No account? Register instead'
              : 'Have an account? Sign in'}
          </button>
        </div>
      </motion.div>
    </motion.div>,
    document.body,
  );
}

function AuthControls() {
  const user = useMarketStore((s) => s.user);
  const logout = useMarketStore((s) => s.logout);
  const [showModal, setShowModal] = useState(false);

  if (user) {
    return (
      <div className="flex items-center gap-2 text-xs">
        <span className="flex h-6 w-6 items-center justify-center rounded-full
          bg-gradient-to-br from-sky-500 to-cyan-400 text-[10px] font-black
          text-slate-950" aria-hidden>
          {user.username.slice(0, 1).toUpperCase()}
        </span>
        <span className="text-slate-300">{user.username}</span>
        <button onClick={logout} data-testid="auth-logout"
          className="rounded-md border border-slate-700 px-2.5 py-1
            text-slate-300 transition-colors hover:border-rose-500/40
            hover:bg-rose-500/10 hover:text-rose-300">
          Sign out</button>
      </div>
    );
  }
  return (
    <>
      <button onClick={() => setShowModal(true)} data-testid="auth-open"
        className="rounded-lg bg-gradient-to-r from-sky-500 to-cyan-400
          px-3.5 py-1.5 text-xs font-bold text-slate-950 shadow-md
          shadow-sky-500/25 transition-all hover:from-sky-400
          hover:to-cyan-300 hover:shadow-lg hover:shadow-sky-500/30">
        Sign in / Register
      </button>
      <AnimatePresence>
        {showModal && <AuthModal onClose={() => setShowModal(false)} />}
      </AnimatePresence>
    </>
  );
}

export default function Header() {
  const bootstrapUser = useMarketStore((s) => s.bootstrapUser);
  useEffect(() => { void bootstrapUser(); }, [bootstrapUser]);

  return (
    <header className="sticky top-0 z-40 flex flex-wrap items-center
      justify-between gap-3 border-b border-slate-800/80 bg-slate-950/85
      px-4 py-3 backdrop-blur-md" data-testid="app-header">
      <div className="flex items-center gap-2.5">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg
          bg-gradient-to-br from-sky-500/25 to-cyan-400/10 ring-1 ring-inset
          ring-sky-500/30 text-base" aria-hidden>🛰️</span>
        <div className="leading-tight">
          <h1 className="bg-gradient-to-r from-sky-300 to-cyan-200
            bg-clip-text text-base font-black tracking-widest
            text-transparent">ORION</h1>
          <span className="hidden text-[9px] uppercase tracking-[0.2em]
            text-slate-500 sm:block">Global Market Intelligence</span>
        </div>
      </div>
      <RegionPills />
      <div className="flex items-center gap-3">
        <SearchBar />
        <AuthControls />
      </div>
    </header>
  );
}


