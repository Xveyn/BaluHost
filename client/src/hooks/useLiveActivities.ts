import { useMemo } from 'react';
import { useAsyncData } from './useAsyncData';
import { getFanStatus, type FanStatusResponse } from '../api/fan-control';
import { getPowerStatus, type PowerStatusResponse } from '../api/power-management';
import type { SchedulerStatus } from '../api/schedulers';
import type { RaidStatusResponse } from '../api/raid';

export interface LiveActivityItem {
  id: string;
  type: 'scheduler_running' | 'fan_scheduled' | 'raid_resync' | 'power_elevated';
  label: string;
  labelParams?: Record<string, string | number>;
  progress?: number;
  icon: 'clock' | 'wind' | 'hard-drive' | 'zap';
  link?: string;
  level: 'info' | 'warning';
}

interface UseLiveActivitiesOptions {
  raidData: RaidStatusResponse | null;
  schedulers: SchedulerStatus[];
  isAdmin: boolean;
}

export function useLiveActivities({ raidData, schedulers, isAdmin }: UseLiveActivitiesOptions) {
  const { data: fanData } = useAsyncData<FanStatusResponse>(getFanStatus, {
    refreshInterval: 30000,
    enabled: isAdmin,
  });

  const { data: powerData } = useAsyncData<PowerStatusResponse>(getPowerStatus, {
    refreshInterval: 15000,
    enabled: isAdmin,
  });

  const activities = useMemo<LiveActivityItem[]>(() => {
    const items: LiveActivityItem[] = [];

    // Running schedulers
    for (const scheduler of schedulers) {
      if (scheduler.is_running) {
        items.push({
          id: `scheduler-${scheduler.name}`,
          type: 'scheduler_running',
          label: 'liveActivities.schedulerRunning',
          labelParams: { name: scheduler.display_name },
          icon: 'clock',
          link: '/schedulers',
          level: 'info',
        });
      }
    }

    // Fans in SCHEDULED mode with active schedule
    if (fanData) {
      for (const fan of fanData.fans) {
        if (fan.mode === 'scheduled' && fan.active_schedule) {
          items.push({
            id: `fan-${fan.fan_id}`,
            type: 'fan_scheduled',
            label: 'liveActivities.fanScheduled',
            labelParams: {
              name: fan.active_schedule.name,
              until: fan.active_schedule.end_time,
            },
            icon: 'wind',
            link: '/system?tab=fans',
            level: 'info',
          });
        }
      }
    }

    // RAID resync/rebuild
    if (raidData) {
      for (const array of raidData.arrays) {
        if (
          array.resync_progress != null &&
          array.resync_progress < 100
        ) {
          const action = array.status === 'rebuilding' ? 'rebuild' : 'check';
          items.push({
            id: `raid-${array.name}`,
            type: 'raid_resync',
            label: 'liveActivities.raidResync',
            labelParams: {
              name: array.name,
              action,
              progress: Math.round(array.resync_progress),
            },
            progress: array.resync_progress,
            icon: 'hard-drive',
            link: '/raid',
            level: action === 'rebuild' ? 'warning' : 'info',
          });
        }
      }
    }

    // Elevated power demands
    if (powerData) {
      const elevatedDemands = powerData.active_demands.filter(
        (d) => d.level === 'medium' || d.level === 'surge'
      );
      if (elevatedDemands.length > 0) {
        const highest = elevatedDemands.find((d) => d.level === 'surge') || elevatedDemands[0];
        items.push({
          id: 'power-elevated',
          type: 'power_elevated',
          label: 'liveActivities.powerElevated',
          labelParams: {
            profile: highest.level.charAt(0).toUpperCase() + highest.level.slice(1),
            source: highest.source,
          },
          icon: 'zap',
          link: '/system?tab=power',
          level: highest.level === 'surge' ? 'warning' : 'info',
        });
      }
    }

    return items;
  }, [schedulers, fanData, raidData, powerData]);

  return { activities };
}
