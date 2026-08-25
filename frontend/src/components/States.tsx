import { motion } from 'framer-motion';

export function LoadingSpinner({ label }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 gap-3">
      <div className="h-8 w-8 animate-spin rounded-full border-2
        border-slate-700 border-t-sky-400" aria-label="loading" />
      <p className="text-xs text-slate-500">{label ?? 'Loading market data…'}</p>
    </div>
  );
}

export function ErrorState({ message, onRetry }: {
  message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 gap-3">
      <span className="text-2xl" role="img" aria-label="warning">⚠️</span>
      <p className="text-sm text-rose-400">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="rounded-md border
          border-slate-600 px-3 py-1 text-xs text-slate-300
          hover:bg-slate-800 transition-colors">
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 gap-2">
      <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }}
        className="text-sm text-slate-500">{message}</motion.span>
    </div>
  );
}
