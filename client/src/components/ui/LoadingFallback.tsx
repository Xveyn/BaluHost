interface LoadingFallbackProps {
  /**
   * 'full' (default) fills the viewport — for top-level/page-level fallbacks
   * that render before Layout is mounted (App.tsx's outer route Suspense, the
   * SetupWizard Suspense).
   * 'inline' fills a smaller area — for fallbacks nested *inside* Layout's
   * content area (AppLayout's inner Suspense around Outlet). Layout's header
   * is fixed (72px, 112px when impersonating) and the fallback renders below
   * it inside <main>, so `min-h-screen` there would push the page taller than
   * the viewport and pop a scrollbar on every slow page-chunk load.
   */
  size?: 'full' | 'inline';
}

export function LoadingFallback({ size = 'full' }: LoadingFallbackProps = {}) {
  return (
    <div className={`flex items-center justify-center ${size === 'full' ? 'min-h-screen' : 'min-h-[50vh]'}`}>
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-600 border-t-sky-500" />
        <p className="text-sm text-slate-500">Loading...</p>
      </div>
    </div>
  );
}
