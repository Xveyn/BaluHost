import { Zap, Volume2, Gauge, ChevronDown } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { FanCurveProfile } from '../../../api/fan-control';

interface FanPresetProfileButtonsProps {
  isReadOnly: boolean;
  systemProfiles: FanCurveProfile[];
  userProfiles: FanCurveProfile[];
  showMoreProfiles: boolean;
  onToggleMore: () => void;
  onApplyPreset: (preset: string) => void;
  onApplyProfile: (profile: FanCurveProfile) => void;
}

export default function FanPresetProfileButtons({
  isReadOnly, systemProfiles, userProfiles, showMoreProfiles,
  onToggleMore, onApplyPreset, onApplyProfile,
}: FanPresetProfileButtonsProps) {
  const { t } = useTranslation(['system', 'common']);

  if (isReadOnly) return null;

  return (
    <div className="flex gap-2 flex-wrap items-center">
      {/* System profiles (or fallback to hardcoded presets) */}
      {systemProfiles.length > 0 ? (
        systemProfiles.map(p => {
          const icons: Record<string, typeof Volume2> = { silent: Volume2, balanced: Gauge, performance: Zap };
          const Icon = icons[p.name] ?? Gauge;
          return (
            <button
              key={p.id}
              onClick={() => onApplyProfile(p)}
              className="px-3 py-1.5 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 text-sm flex items-center gap-1.5 transition-colors"
              title={p.description ?? ''}
            >
              <Icon className="w-4 h-4" />
              {p.name.charAt(0).toUpperCase() + p.name.slice(1)}
            </button>
          );
        })
      ) : (
        <>
          <button
            onClick={() => onApplyPreset('silent')}
            className="px-3 py-1.5 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 text-sm flex items-center gap-1.5 transition-colors"
            title={t('system:fanControl.presets.silentDesc')}
          >
            <Volume2 className="w-4 h-4" />
            {t('system:fanControl.presets.silent')}
          </button>
          <button
            onClick={() => onApplyPreset('balanced')}
            className="px-3 py-1.5 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 text-sm flex items-center gap-1.5 transition-colors"
            title={t('system:fanControl.presets.balancedDesc')}
          >
            <Gauge className="w-4 h-4" />
            {t('system:fanControl.presets.balanced')}
          </button>
          <button
            onClick={() => onApplyPreset('performance')}
            className="px-3 py-1.5 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 text-sm flex items-center gap-1.5 transition-colors"
            title={t('system:fanControl.presets.performanceDesc')}
          >
            <Zap className="w-4 h-4" />
            {t('system:fanControl.presets.performance')}
          </button>
        </>
      )}

      {/* User profiles dropdown */}
      {userProfiles.length > 0 && (
        <div className="relative">
          <button
            onClick={onToggleMore}
            className="px-3 py-1.5 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 text-sm flex items-center gap-1.5 transition-colors"
          >
            {t('system:fanControl.profiles.more')}
            <ChevronDown className={`w-3 h-3 transition-transform ${showMoreProfiles ? 'rotate-180' : ''}`} />
          </button>
          {showMoreProfiles && (
            <div className="absolute right-0 top-full mt-1 z-10 bg-slate-800 border border-slate-700 rounded-lg shadow-xl py-1 min-w-[160px]">
              {userProfiles.map(p => (
                <button
                  key={p.id}
                  onClick={() => onApplyProfile(p)}
                  className="w-full text-left px-3 py-2 text-sm text-slate-300 hover:bg-slate-700 transition-colors"
                >
                  {p.name}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
