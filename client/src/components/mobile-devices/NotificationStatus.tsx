import { useQuery } from '@tanstack/react-query';
import { Bell } from 'lucide-react';
import { getDeviceNotifications } from '../../api/mobile';
import { queryKeys } from '../../lib/queryKeys';
import { notificationTimeAgo } from './mobileDeviceDates';

/**
 * Component to display last notification sent to device.
 */
export function NotificationStatus({ deviceId }: { deviceId: string }) {
  const { data: notifications = [] } = useQuery({
    queryKey: queryKeys.mobile.deviceNotifications(deviceId),
    queryFn: () => getDeviceNotifications(deviceId, 1),
  });
  const lastNotification = notifications[0] ?? null;

  if (!lastNotification) return null;

  const notificationLabels: Record<string, string> = {
    '7_days': '7 Tage Warnung',
    '3_days': '3 Tage Warnung',
    '1_hour': '1 Stunde Warnung',
  };

  const notificationLabel = notificationLabels[lastNotification.notification_type] || lastNotification.notification_type;
  const timeAgo = notificationTimeAgo(lastNotification.sent_at);

  return (
    <div className="mt-3 pt-3 border-t border-slate-700/50">
      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
        <Bell className={`w-3.5 h-3.5 ${
          lastNotification.success ? 'text-sky-400' : 'text-red-400'
        }`} />
        <span className="font-medium text-slate-300">Letzte Benachrichtigung:</span>
        <span>{notificationLabel}</span>
        <span className="text-slate-500">•</span>
        <span>{timeAgo}</span>
        {!lastNotification.success && (
          <span className="text-red-400 font-semibold">Fehlgeschlagen</span>
        )}
      </div>
    </div>
  );
}
