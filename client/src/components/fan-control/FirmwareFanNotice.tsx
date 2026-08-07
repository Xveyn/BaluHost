import { useTranslation } from 'react-i18next';
import { Cpu } from 'lucide-react';

export default function FirmwareFanNotice() {
  const { t } = useTranslation(['system']);

  return (
    <div className="border border-sky-500/30 bg-sky-500/5 rounded p-3">
      <div className="flex items-start gap-2">
        <Cpu size={16} className="text-sky-400 mt-0.5" />
        <div className="flex-1">
          <div className="text-sm font-medium text-white">
            {t('system:fanControl.gpu.firmware.title')}
          </div>
          <div className="text-xs text-slate-400 mt-1">
            {t('system:fanControl.gpu.firmware.explanation')}
          </div>
        </div>
      </div>
    </div>
  );
}
