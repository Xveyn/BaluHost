import { useMemo } from 'react';
import {
  DndContext, closestCenter, KeyboardSensor, PointerSensor,
  useSensor, useSensors,
} from '@dnd-kit/core';
import type { DragEndEvent } from '@dnd-kit/core';
import {
  SortableContext, sortableKeyboardCoordinates, verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';
import { usePillConfig } from './usePillConfig';
import { PillRow } from './PillRow';
import { TopbarStatusStrip } from '../topbar/TopbarStatusStrip';
import type { StatusBarStateResponse } from '../../api/statusBar';

export function StatusBarConfigTab() {
  const { t } = useTranslation('statusBar');
  const cfg = usePillConfig();
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const from = cfg.pills.findIndex(p => p.pill_id === active.id);
    const to = cfg.pills.findIndex(p => p.pill_id === over.id);
    if (from >= 0 && to >= 0) cfg.reorder(from, to);
  };

  const onSave = async () => {
    try {
      await cfg.save();
      toast.success(t('saved'));
    } catch {
      toast.error(t('saveFailed'));
    }
  };

  const previewState: StatusBarStateResponse = useMemo(() => ({
    pills: cfg.pills
      .filter(p => p.enabled)
      .map(p => ({
        id: p.pill_id, kind: 'state' as const, tone: 'neutral' as const,
        // Preview shows the config name; strip the "statusBar." ns prefix so the
        // renderer's useTranslation('statusBar') resolves it.
        label_key: p.name_key.replace(/^statusBar\./, ''),
        href: p.href, value: null, value_key: null, value_params: null, icon: p.icon, extra: null,
        // Plugin pills carry their own translations/literal fallback — without
        // these PillRenderer falls back to t() and prints the raw i18n key.
        translations: p.translations,
        label_text: p.name_text,
      })),
    show_bottom_upload: cfg.showBottomUpload,
  }), [cfg.pills, cfg.showBottomUpload]);

  if (cfg.loading) {
    return <div className="py-8 text-center text-slate-400">…</div>;
  }
  if (cfg.error) {
    return <div className="py-8 text-center text-rose-400">{t('loadFailed')}</div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-white">{t('tabTitle')}</h2>
        <p className="mt-1 text-sm text-slate-400">{t('description')}</p>
      </div>

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={cfg.pills.map(p => p.pill_id)} strategy={verticalListSortingStrategy}>
          <div className="space-y-2">
            {cfg.pills.map(entry => (
              <PillRow
                key={entry.pill_id}
                entry={entry}
                onToggleEnabled={cfg.setEnabled}
                onSetVisibility={cfg.setVisibility}
                onSetDisplayMode={cfg.setDisplayMode}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>

      <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-3">
        <div>
          <p className="text-sm text-slate-200">{t('uploadBar.title')}</p>
          <p className="text-xs text-slate-500">{t('uploadBar.desc')}</p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={cfg.showBottomUpload}
          aria-label={t('uploadBar.title')}
          onClick={() => cfg.setShowBottomUpload(!cfg.showBottomUpload)}
          className={`relative h-5 w-9 rounded-full transition ${cfg.showBottomUpload ? 'bg-emerald-500/70' : 'bg-slate-700'}`}
        >
          <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${cfg.showBottomUpload ? 'left-4' : 'left-0.5'}`} />
        </button>
      </div>

      <div className="rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-3">
        <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">{t('preview.title')}</p>
        {previewState.pills.length === 0
          ? <p className="text-sm text-slate-500">{t('preview.empty')}</p>
          : <TopbarStatusStrip previewState={previewState} />}
      </div>

      <div className="flex items-center gap-3">
        <button type="button" onClick={onSave} disabled={cfg.saving} className="btn btn-primary">
          {t('save')}
        </button>
        <button type="button" onClick={cfg.reload} disabled={cfg.saving} className="btn btn-secondary">
          {t('reset')}
        </button>
      </div>
    </div>
  );
}
