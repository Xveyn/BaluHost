import { Table, LineChart as LineChartIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface FanCurveGraphControlsProps {
  viewMode: 'chart' | 'table';
  onViewModeChange: (mode: 'chart' | 'table') => void;
  hasUnsavedChanges: boolean;
  isReadOnly: boolean;
  onSave: () => void;
  onDiscard: () => void;
}

export default function FanCurveGraphControls({
  viewMode, onViewModeChange, hasUnsavedChanges, isReadOnly, onSave, onDiscard,
}: FanCurveGraphControlsProps) {
  const { t } = useTranslation(['system', 'common']);

  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
      <p className="text-sm text-slate-400">
        {t('system:fanControl.curve.configureInfo')}
      </p>
      <div className="flex gap-2 items-center">
        {/* View Mode Toggle */}
        <div className="flex gap-1 bg-slate-800 rounded-lg p-1">
          <button
            onClick={() => onViewModeChange('chart')}
            className={`px-3 py-1 text-xs rounded-md transition-colors flex items-center gap-1 ${
              viewMode === 'chart'
                ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/30'
                : 'text-slate-400 hover:text-slate-300'
            }`}
          >
            <LineChartIcon className="w-3 h-3" />
            {t('system:fanControl.curve.chart')}
          </button>
          <button
            onClick={() => onViewModeChange('table')}
            className={`px-3 py-1 text-xs rounded-md transition-colors flex items-center gap-1 ${
              viewMode === 'table'
                ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/30'
                : 'text-slate-400 hover:text-slate-300'
            }`}
          >
            <Table className="w-3 h-3" />
            {t('system:fanControl.curve.table')}
          </button>
        </div>

        {/* Save/Discard Buttons - only shown when there are unsaved changes */}
        {hasUnsavedChanges && !isReadOnly && (
          <div className="flex gap-2">
            <button
              onClick={onDiscard}
              className="px-4 py-2 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 text-sm"
            >
              {t('system:fanControl.curve.discard')}
            </button>
            <button
              onClick={onSave}
              className="px-4 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 shadow-lg shadow-emerald-500/30 text-sm"
            >
              {t('system:fanControl.curve.save')}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
