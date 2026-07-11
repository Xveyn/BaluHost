export function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 rounded-full transition-colors ${
        checked ? 'bg-teal-500' : 'bg-slate-600'
      }`}
    >
      <span
        className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow transform transition-transform ${
          checked ? 'translate-x-5.5 ml-0.5' : 'translate-x-0.5'
        } mt-0.5`}
      />
    </button>
  );
}

export function ToggleRow({
  label,
  checked,
  onChange,
  icon,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  icon?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        {icon}
        <span className="text-xs sm:text-sm text-slate-300">{label}</span>
      </div>
      <Toggle checked={checked} onChange={onChange} />
    </div>
  );
}

export function NumberInput({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <label className="text-xs sm:text-sm text-slate-400 shrink-0">{label}</label>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        min={min}
        max={max}
        step={step}
        className="w-24 rounded bg-slate-900 border border-slate-600 px-3 py-1.5 text-sm text-white text-right focus:border-teal-400 focus:outline-none"
      />
    </div>
  );
}
