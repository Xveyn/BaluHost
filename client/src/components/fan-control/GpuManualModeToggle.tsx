import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { AlertTriangle } from 'lucide-react';
import { setGpuManualMode } from '../../api/fan-control';
import { handleApiError } from '../../lib/errorHandling';

interface Props {
  fanId: string;
  enabled: boolean;
  onChange: (enabled: boolean) => void;
}

export default function GpuManualModeToggle({ fanId, enabled, onChange }: Props) {
  const { t } = useTranslation(['system']);
  const [busy, setBusy] = useState(false);

  const toggle = async () => {
    setBusy(true);
    try {
      await setGpuManualMode(fanId, !enabled);
      onChange(!enabled);
      toast.success(
        enabled
          ? t('system:fanControl.gpu.manualMode.disabled')
          : t('system:fanControl.gpu.manualMode.enabled')
      );
    } catch (err) {
      handleApiError(err, t('system:fanControl.gpu.manualMode.title'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border border-yellow-500/30 bg-yellow-500/5 rounded p-3 space-y-2">
      <div className="flex items-start gap-2">
        <AlertTriangle size={16} className="text-yellow-500 mt-0.5" />
        <div className="flex-1">
          <div className="text-sm font-medium text-white">{t('system:fanControl.gpu.manualMode.title')}</div>
          <div className="text-xs text-slate-400">{t('system:fanControl.gpu.manualMode.warning')}</div>
        </div>
      </div>
      <button
        onClick={toggle}
        disabled={busy}
        className={`px-3 py-1 text-sm rounded ${enabled ? 'bg-rose-500 text-white' : 'bg-sky-500 text-white'}`}
      >
        {enabled ? t('system:fanControl.gpu.manualMode.disable') : t('system:fanControl.gpu.manualMode.enable')}
      </button>
    </div>
  );
}
