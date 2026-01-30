/**
 * Hook for getting the next scheduled maintenance
 */
import { useMemo } from 'react';
import { useSchedulers } from './useSchedulers';
import type { SchedulerStatus } from '../api/schedulers';

export interface NextMaintenance {
  scheduler: SchedulerStatus;
  nextRunAt: Date;
  isOverdue: boolean;
}

interface UseNextMaintenanceOptions {
  refreshInterval?: number;
  enabled?: boolean;
}

interface UseNextMaintenanceReturn {
  nextMaintenance: NextMaintenance | null;
  allSchedulers: SchedulerStatus[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useNextMaintenance(options: UseNextMaintenanceOptions = {}): UseNextMaintenanceReturn {
  const { refreshInterval = 60000, enabled = true } = options;

  const { schedulers, loading, error, refetch } = useSchedulers({
    refreshInterval,
    enabled,
  });

  const nextMaintenance = useMemo<NextMaintenance | null>(() => {
    if (!schedulers || schedulers.length === 0) {
      return null;
    }

    // Find enabled scheduler with earliest next_run_at
    const now = new Date();
    let earliest: NextMaintenance | null = null;

    for (const scheduler of schedulers) {
      if (!scheduler.is_enabled || !scheduler.next_run_at) {
        continue;
      }

      const nextRunAt = new Date(scheduler.next_run_at);
      const isOverdue = nextRunAt < now;

      if (!earliest || nextRunAt < earliest.nextRunAt) {
        earliest = {
          scheduler,
          nextRunAt,
          isOverdue,
        };
      }
    }

    return earliest;
  }, [schedulers]);

  return {
    nextMaintenance,
    allSchedulers: schedulers,
    loading,
    error,
    refetch,
  };
}

// Helper: format next run time
export function formatNextRun(date: Date): string {
  const now = new Date();
  const diffMs = date.getTime() - now.getTime();
  const diffMinutes = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMs < 0) {
    // Overdue
    return 'Overdue';
  }

  if (diffMinutes < 60) {
    return `in ${diffMinutes} min`;
  }
  if (diffHours < 24) {
    return `in ${diffHours}h`;
  }
  if (diffDays < 7) {
    return `in ${diffDays} day${diffDays === 1 ? '' : 's'}`;
  }

  // Format as date
  return date.toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  });
}

// Helper: format date window
export function formatScheduleWindow(date: Date): string {
  const dayName = date.toLocaleDateString(undefined, { weekday: 'long' });
  const dateStr = date.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
  const timeStr = date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });

  return `${dayName} - ${dateStr} - ${timeStr}`;
}
