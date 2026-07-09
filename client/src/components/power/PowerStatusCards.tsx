import { useTranslation } from 'react-i18next';
import { StatCard } from '../ui/StatCard';
import { getPresetIcon } from './utils';
import {
  PROFILE_INFO,
  PROPERTY_INFO,
  formatClockSpeed,
  type PowerStatusResponse,
  type PowerDemandInfo,
  type ServicePowerProperty,
  type PowerPreset,
} from '../../api/power-management';

interface PowerStatusCardsProps {
  status: PowerStatusResponse | null;
  activePreset?: PowerPreset;
  currentProperty?: ServicePowerProperty;
  demands: PowerDemandInfo[];
  lastUpdated: Date | null;
}

export function PowerStatusCards({
  status, activePreset, currentProperty, demands, lastUpdated,
}: PowerStatusCardsProps) {
  const { t } = useTranslation(['system', 'common']);
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard
        label={t('system:power.statusCards.activePreset')}
        value={status?.dynamic_mode_enabled ? t('system:power.dynamicMode.title') : (activePreset?.name || '-')}
        subValue={status?.dynamic_mode_enabled ? status.target_frequency_range : activePreset?.description}
        color={status?.dynamic_mode_enabled ? 'teal' : activePreset?.name.includes('Performance') ? 'red' : activePreset?.name.includes('Energy') ? 'emerald' : 'blue'}
        icon={<span className="text-2xl">{status?.dynamic_mode_enabled ? '\u{26A1}' : activePreset ? getPresetIcon(activePreset.name) : '\u{26A1}'}</span>}
      />
      <StatCard
        label={t('system:power.statusCards.currentProperty')}
        value={currentProperty ? PROPERTY_INFO[currentProperty].name : '-'}
        subValue={currentProperty ? t(`system:power.propertyDescription.${currentProperty}`) : undefined}
        color={PROFILE_INFO[currentProperty || 'idle']?.color || 'slate'}
        icon={<span className="text-2xl">{currentProperty ? PROPERTY_INFO[currentProperty].icon : '⚡'}</span>}
      />
      <StatCard
        label={t('system:power.statusCards.cpuFrequency')}
        value={status?.current_frequency_mhz ? formatClockSpeed(status.current_frequency_mhz) : '-'}
        subValue={status?.target_frequency_range
          ? `${t('system:power.statusCards.targetBand')}: ${status.target_frequency_range}`
          : lastUpdated
            ? `${t('system:power.statusCards.updated')}: ${lastUpdated.toLocaleTimeString()}`
            : undefined}
        color="blue"
        icon={
          <svg className="h-6 w-6 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        }
      />
      <StatCard
        label={t('system:power.statusCards.activeDemands')}
        value={demands.length}
        subValue={demands.length > 0 ? `${t('system:power.statusCards.highest')}: ${PROPERTY_INFO[(demands.reduce((a, b) =>
          ['surge', 'medium', 'low', 'idle'].indexOf((a.power_property || a.level) as string) <
          ['surge', 'medium', 'low', 'idle'].indexOf((b.power_property || b.level) as string) ? a : b
        ).power_property || demands[0].level) as ServicePowerProperty].name}` : t('system:power.statusCards.none')}
        color="purple"
        icon={
          <svg className="h-6 w-6 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
        }
      />
    </div>
  );
}
