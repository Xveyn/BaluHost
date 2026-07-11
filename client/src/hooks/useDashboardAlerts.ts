import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { Alert } from '../components/dashboard';
import type { SmartStatusResponse } from '../api/smart';
import type { RaidStatusResponse } from '../api/raid';
import type { SchedulerStatus } from '../api/schedulers';
import type { ServiceStatus } from '../api/service-status';

export interface UseDashboardAlertsInput {
  smartData: SmartStatusResponse | null;
  raidData: RaidStatusResponse | null;
  allSchedulers: SchedulerStatus[];
  services: ServiceStatus[];
  isAdmin: boolean;
}

export function useDashboardAlerts({
  smartData,
  raidData,
  allSchedulers,
  services,
  isAdmin,
}: UseDashboardAlertsInput): Alert[] {
  const { t } = useTranslation('dashboard');

  // Generate alerts from various sources
  const alerts = useMemo<Alert[]>(() => {
    const result: Alert[] = [];

    // SMART alerts — split FAILED (critical) vs UNKNOWN (warning)
    if (smartData) {
      const failedDevices = smartData.devices.filter(d => d.status === 'FAILED');
      const unknownDevices = smartData.devices.filter(d => d.status === 'UNKNOWN');
      if (failedDevices.length > 0) {
        result.push({
          id: 'smart-failure',
          type: 'critical',
          title: t('alerts.smartFailure.title'),
          message: t('alerts.smartFailure.message', { count: failedDevices.length }),
          link: '/system',
          linkText: t('alerts.viewDetails'),
          source: 'smart',
        });
      }
      if (unknownDevices.length > 0) {
        result.push({
          id: 'smart-unknown',
          type: 'warning',
          title: t('alerts.smartUnknown.title'),
          message: t('alerts.smartUnknown.message', { count: unknownDevices.length }),
          link: '/system',
          linkText: t('alerts.viewDetails'),
          source: 'smart',
        });
      }
    }

    // RAID alerts
    if (raidData && raidData.arrays.some(a => a.status.includes('degraded'))) {
      const degradedArrays = raidData.arrays.filter(a => a.status.includes('degraded'));
      result.push({
        id: 'raid-degraded',
        type: 'critical',
        title: t('alerts.raidDegraded.title'),
        message: t('alerts.raidDegraded.message', { count: degradedArrays.length }),
        link: '/raid',
        linkText: t('alerts.viewRaid'),
        source: 'raid',
      });
    }

    // Scheduler alerts (only for admin)
    if (isAdmin && allSchedulers.some(s => s.last_status === 'failed')) {
      const failedSchedulers = allSchedulers.filter(s => s.last_status === 'failed');
      result.push({
        id: 'scheduler-failed',
        type: 'warning',
        title: t('alerts.schedulerFailed.title'),
        message: t('alerts.schedulerFailed.message', { count: failedSchedulers.length }),
        link: '/schedulers',
        linkText: t('alerts.viewSchedulers'),
        source: 'scheduler',
      });
    }

    // Service alerts (only for admin)
    if (isAdmin && services.some(s => s.state === 'error')) {
      const errorServices = services.filter(s => s.state === 'error');
      result.push({
        id: 'service-error',
        type: 'warning',
        title: t('alerts.serviceError.title'),
        message: t('alerts.serviceError.message', { count: errorServices.length }),
        link: '/health',
        linkText: t('alerts.viewHealth'),
        source: 'service',
      });
    }

    return result;
  }, [smartData, raidData, allSchedulers, services, isAdmin, t]);

  return alerts;
}
