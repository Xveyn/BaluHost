export function CacheArraySelector({
  arrays,
  selectedArray,
  onSelect,
}: {
  arrays: string[];
  selectedArray: string;
  onSelect: (name: string) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-slate-400">Array:</span>
      <div className="flex gap-1.5">
        {arrays.map((name) => (
          <button
            key={name}
            onClick={() => onSelect(name)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${
              name === selectedArray
                ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40'
                : 'bg-slate-800/60 text-slate-400 border border-slate-700/50 hover:border-slate-600'
            }`}
          >
            {name}
          </button>
        ))}
      </div>
    </div>
  );
}
