export function ApiLoadingSkeleton() {
  return (
    <div className="space-y-4">
      {[1, 2, 3].map(i => (
        <div key={i} className="animate-pulse">
          <div className="h-6 bg-slate-800/60 rounded w-48 mb-3" />
          <div className="space-y-2">
            <div className="h-14 bg-slate-800/40 rounded-xl" />
            <div className="h-14 bg-slate-800/40 rounded-xl" />
          </div>
        </div>
      ))}
    </div>
  );
}
