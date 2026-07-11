import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { localRangeToUtcIso } from '../../../lib/dateUtils';

interface CustomRangePickerProps {
  active: boolean;
  onApply: (startIso: string, endIso: string) => void;
}

export function CustomRangePicker({ active, onApply }: CustomRangePickerProps) {
  const { t } = useTranslation(['system', 'common']);
  const [showRangePicker, setShowRangePicker] = useState(false);
  const [draftStart, setDraftStart] = useState('');
  const [draftEnd, setDraftEnd] = useState('');

  return (
    <div className="relative">
      <button
        onClick={() => setShowRangePicker((v) => !v)}
        className={`px-3 py-1.5 text-xs sm:text-sm rounded-md transition-colors ${
          active
            ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
            : 'bg-slate-800 text-slate-400 hover:bg-slate-700 border border-transparent'
        }`}
      >
        {t('monitor.power.periodCustom')}
      </button>
      {showRangePicker && (
        <div
          className="absolute right-0 z-20 mt-2 w-64 rounded-lg border border-slate-700 bg-slate-900 p-3 shadow-xl"
          onKeyDown={(e) => { if (e.key === 'Escape') setShowRangePicker(false); }}
        >
          <label className="block text-xs text-slate-400 mb-1">{t('monitor.power.customFrom')}</label>
          <input
            type="date"
            value={draftStart}
            max={draftEnd || undefined}
            onChange={(e) => setDraftStart(e.target.value)}
            className="w-full mb-2 px-2 py-1 text-sm bg-slate-800 border border-slate-700 rounded text-white focus:border-blue-500 focus:outline-none"
          />
          <label className="block text-xs text-slate-400 mb-1">{t('monitor.power.customTo')}</label>
          <input
            type="date"
            value={draftEnd}
            min={draftStart || undefined}
            onChange={(e) => setDraftEnd(e.target.value)}
            className="w-full mb-3 px-2 py-1 text-sm bg-slate-800 border border-slate-700 rounded text-white focus:border-blue-500 focus:outline-none"
          />
          <button
            onClick={() => {
              if (!draftStart || !draftEnd || draftStart > draftEnd) {
                toast.error(t('monitor.power.customInvalidRange'));
                return;
              }
              const { startIso, endIso } = localRangeToUtcIso(draftStart, draftEnd, Date.now());
              onApply(startIso, endIso);
              setShowRangePicker(false);
            }}
            className="w-full px-2 py-1.5 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded"
          >
            {t('monitor.power.customApply')}
          </button>
        </div>
      )}
    </div>
  );
}
