import type { EnergyPriceConfig } from '../../../api/energy';
import { formatNumber } from '../../../lib/formatters';

interface EnergyPriceEditorProps {
  priceConfig: EnergyPriceConfig;
  editing: boolean;
  priceInput: string;
  saving: boolean;
  onEdit: () => void;
  onInputChange: (v: string) => void;
  onSave: () => void;
  onCancel: () => void;
}

export function EnergyPriceEditor({
  priceConfig,
  editing,
  priceInput,
  saving,
  onEdit,
  onInputChange,
  onSave,
  onCancel,
}: EnergyPriceEditorProps) {
  return (
    <div className="flex items-center gap-2">
      {editing ? (
        <div className="flex items-center gap-2">
          <input
            type="number"
            step="0.01"
            min="0.01"
            max="10"
            value={priceInput}
            onChange={(e) => onInputChange(e.target.value)}
            className="w-20 px-2 py-1 text-sm bg-slate-800 border border-slate-700 rounded text-white focus:border-blue-500 focus:outline-none"
            disabled={saving}
          />
          <span className="text-slate-400 text-sm">{priceConfig.currency}/kWh</span>
          <button
            onClick={onSave}
            disabled={saving}
            className="px-2 py-1 text-xs bg-green-600 hover:bg-green-700 text-white rounded disabled:opacity-50"
          >
            {saving ? '...' : '✓'}
          </button>
          <button
            onClick={onCancel}
            disabled={saving}
            className="px-2 py-1 text-xs bg-slate-700 hover:bg-slate-600 text-white rounded disabled:opacity-50"
          >
            ✕
          </button>
        </div>
      ) : (
        <button
          onClick={onEdit}
          className="flex items-center gap-1 px-2 py-1 text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700"
        >
          <span>{formatNumber(priceConfig.cost_per_kwh, 2)} {priceConfig.currency}/kWh</span>
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
          </svg>
        </button>
      )}
    </div>
  );
}
