import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical, Lock } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { CSSProperties } from 'react';
import { resolvePluginString } from '../../lib/pluginI18n';
import type { PillCatalogEntry, PillVisibility, DisplayMode } from '../../api/statusBar';

interface Props {
  entry: PillCatalogEntry;
  onToggleEnabled: (id: string, enabled: boolean) => void;
  onSetVisibility: (id: string, visibility: PillVisibility) => void;
  onSetDisplayMode: (id: string, displayMode: DisplayMode) => void;
}

export function PillRow({ entry, onToggleEnabled, onSetVisibility, onSetDisplayMode }: Props) {
  const { t } = useTranslation('statusBar');
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: entry.pill_id });

  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="flex items-center gap-3 rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2"
    >
      <button
        type="button"
        className="cursor-grab text-slate-500 hover:text-slate-300 touch-none"
        aria-label="drag handle"
        {...attributes}
        {...listeners}
      >
        <GripVertical className="h-4 w-4" />
      </button>

      {/* Backend sends name_key as a fully-qualified i18next key with a dot-prefixed
          namespace ("statusBar.pills.power.name"). useTranslation('statusBar') already
          binds the namespace, so strip the leading "statusBar." to pass the ns-relative key. */}
      <span className="flex-1 text-sm text-slate-200">
        {entry.translations
          ? resolvePluginString(entry.translations, entry.name_key, entry.name_text ?? entry.pill_id)
          : t(entry.name_key.replace(/^statusBar\./, ''))}
      </span>

      {entry.visibility_locked ? (
        <span className="inline-flex items-center gap-1 rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-400">
          <Lock className="h-3 w-3" />
          {t('visibility.locked')}
        </span>
      ) : null}

      {entry.display_mode_configurable ? (
        <select
          aria-label="display mode"
          className="rounded-md border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200"
          value={entry.display_mode}
          onChange={(e) => onSetDisplayMode(entry.pill_id, e.target.value as DisplayMode)}
        >
          <option value="always">{t('displayMode.always')}</option>
          <option value="when_off">{t('displayMode.whenOff')}</option>
          <option value="when_on">{t('displayMode.whenOn')}</option>
        </select>
      ) : null}

      <select
        className="rounded-md border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 disabled:opacity-50"
        value={entry.visibility}
        disabled={entry.visibility_locked}
        onChange={(e) => onSetVisibility(entry.pill_id, e.target.value as PillVisibility)}
      >
        <option value="admin">{t('visibility.admin')}</option>
        <option value="all">{t('visibility.all')}</option>
      </select>

      <button
        type="button"
        role="switch"
        aria-checked={entry.enabled}
        aria-label={t('enabled')}
        onClick={() => onToggleEnabled(entry.pill_id, !entry.enabled)}
        className={`relative h-5 w-9 rounded-full transition ${entry.enabled ? 'bg-emerald-500/70' : 'bg-slate-700'}`}
      >
        <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${entry.enabled ? 'left-4' : 'left-0.5'}`} />
      </button>
    </div>
  );
}
