import { useState, useEffect } from 'react';
import {
  HardDrive,
  Activity,
  Archive,
  Clock,
  Server,
  Shield,
  RefreshCw,
  Globe,
  Bell,
  Loader2,
} from 'lucide-react';
import {
  getUserNotificationRouting,
  updateUserNotificationRouting,
  type UserNotificationRouting,
  type UserNotificationRoutingUpdate,
} from '../../api/notificationRouting';
import { handleApiError } from '../../lib/errorHandling';
import toast from 'react-hot-toast';

interface NotificationRoutingSectionProps {
  userId: number;
  userRole: string;
}

interface RoutingToggle {
  key: keyof UserNotificationRoutingUpdate;
  label: string;
  description: string;
  icon: React.ReactNode;
}

const ROUTING_TOGGLES: RoutingToggle[] = [
  {
    key: 'receive_raid',
    label: 'RAID',
    description: 'RAID-Statusaenderungen und Warnungen',
    icon: <HardDrive className="h-4 w-4" />,
  },
  {
    key: 'receive_smart',
    label: 'SMART',
    description: 'Festplatten-Gesundheitswarnungen',
    icon: <Activity className="h-4 w-4" />,
  },
  {
    key: 'receive_backup',
    label: 'Backup',
    description: 'Backup-Erfolge und -Fehler',
    icon: <Archive className="h-4 w-4" />,
  },
  {
    key: 'receive_scheduler',
    label: 'Scheduler',
    description: 'Geplante Aufgaben Statusmeldungen',
    icon: <Clock className="h-4 w-4" />,
  },
  {
    key: 'receive_system',
    label: 'System',
    description: 'Speicherplatz, Temperatur, Services',
    icon: <Server className="h-4 w-4" />,
  },
  {
    key: 'receive_security',
    label: 'Sicherheit',
    description: 'Fehlgeschlagene Logins, Brute-Force',
    icon: <Shield className="h-4 w-4" />,
  },
  {
    key: 'receive_sync',
    label: 'Sync',
    description: 'Sync-Konflikte und -Fehler',
    icon: <RefreshCw className="h-4 w-4" />,
  },
  {
    key: 'receive_vpn',
    label: 'VPN',
    description: 'VPN-Client-Ablaufwarnungen',
    icon: <Globe className="h-4 w-4" />,
  },
];

export function NotificationRoutingSection({ userId, userRole }: NotificationRoutingSectionProps) {
  const [routing, setRouting] = useState<UserNotificationRouting | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (userRole === 'admin') return;
    setLoading(true);
    getUserNotificationRouting(userId)
      .then(setRouting)
      .catch(() => setRouting(null))
      .finally(() => setLoading(false));
  }, [userId, userRole]);

  if (userRole === 'admin') return null;

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-3 text-sm text-slate-400">
        <Loader2 className="h-4 w-4 animate-spin" />
        Lade Benachrichtigungs-Routing...
      </div>
    );
  }

  const handleToggle = async (key: keyof UserNotificationRoutingUpdate, newValue: boolean) => {
    setSaving(true);
    try {
      const update: UserNotificationRoutingUpdate = { [key]: newValue };
      const result = await updateUserNotificationRouting(userId, update);
      setRouting(result);
      toast.success('Benachrichtigungs-Routing aktualisiert');
    } catch (error) {
      handleApiError(error, 'Fehler beim Speichern');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="border-t border-slate-800 pt-3 mt-3">
      <div className="flex items-center gap-2 mb-1">
        <Bell className="h-4 w-4 text-slate-400" />
        <h3 className="text-sm font-medium text-slate-300">System-Benachrichtigungen</h3>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        Legt fest, welche System-Benachrichtigungen dieser User erhaelt.
      </p>

      <div className="space-y-2">
        {ROUTING_TOGGLES.map((toggle) => {
          const value = routing?.[toggle.key] ?? false;

          return (
            <div key={toggle.key} className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-slate-400">{toggle.icon}</span>
                <div>
                  <span className="text-sm text-slate-200">{toggle.label}</span>
                  <span className="text-xs text-slate-500 ml-2">{toggle.description}</span>
                </div>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={value}
                disabled={saving}
                onClick={() => handleToggle(toggle.key, !value)}
                className={`relative inline-flex h-5 w-9 flex-shrink-0 items-center rounded-full transition-colors
                  ${value ? 'bg-sky-500' : 'bg-slate-700'}
                  ${saving ? 'opacity-50' : 'cursor-pointer'}
                `}
              >
                <span
                  className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform
                    ${value ? 'translate-x-4' : 'translate-x-0.5'}
                  `}
                />
              </button>
            </div>
          );
        })}
      </div>

      {routing?.granted_by_username && (
        <p className="text-xs text-slate-500 mt-2">
          Zuletzt geaendert von {routing.granted_by_username}
          {routing.granted_at && ` am ${new Date(routing.granted_at).toLocaleDateString('de-DE')}`}
        </p>
      )}
    </div>
  );
}
