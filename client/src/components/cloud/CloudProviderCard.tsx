import { Trash2, Clock } from 'lucide-react';
import type { CloudConnection, CloudProvider } from '../../api/cloud-import';
import { PROVIDER_LABELS } from '../../api/cloud-import';

const PROVIDER_COLORS: Record<CloudProvider, string> = {
  google_drive: 'from-blue-500 to-green-500',
  onedrive: 'from-blue-600 to-sky-400',
  icloud: 'from-slate-400 to-slate-200',
};

const PROVIDER_ICONS: Record<CloudProvider, string> = {
  google_drive: 'GD',
  onedrive: 'OD',
  icloud: 'iC',
};

interface CloudProviderCardProps {
  connection: CloudConnection;
  selected: boolean;
  onSelect: () => void;
  onDelete: () => void;
}

export function CloudProviderCard({ connection, selected, onSelect, onDelete }: CloudProviderCardProps) {
  const gradient = PROVIDER_COLORS[connection.provider] || 'from-slate-500 to-slate-400';
  const icon = PROVIDER_ICONS[connection.provider] || '??';
  const label = PROVIDER_LABELS[connection.provider] || connection.provider;

  const lastUsed = connection.last_used_at
    ? new Date(connection.last_used_at).toLocaleDateString()
    : null;

  return (
    <div
      className={`group relative flex items-center gap-3 rounded-xl border p-4 transition-all cursor-pointer ${
        selected
          ? 'border-sky-500/50 bg-sky-500/5 ring-1 ring-sky-500/30'
          : 'border-slate-700/50 bg-slate-800/40 hover:border-slate-600/50 hover:bg-slate-800/60'
      }`}
      onClick={onSelect}
    >
      {/* Provider icon */}
      <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br ${gradient} text-sm font-bold text-white`}>
        {icon}
      </div>

      {/* Info */}
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-slate-200">{connection.display_name}</p>
        <p className="text-xs text-slate-500">{label}</p>
        {lastUsed && (
          <p className="mt-0.5 flex items-center gap-1 text-xs text-slate-600">
            <Clock className="h-3 w-3" />
            {lastUsed}
          </p>
        )}
      </div>

      {/* Status dot */}
      <div className={`h-2 w-2 rounded-full ${connection.is_active ? 'bg-emerald-400' : 'bg-slate-600'}`} />

      {/* Delete button */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        className="rounded-lg p-1.5 text-slate-600 opacity-0 transition-all hover:bg-red-500/10 hover:text-red-400 group-hover:opacity-100"
        title="Delete connection"
      >
        <Trash2 className="h-4 w-4" />
      </button>
    </div>
  );
}
