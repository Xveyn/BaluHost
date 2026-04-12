/**
 * Notification Preferences Page
 *
 * Allows users to configure their notification settings including
 * category filters, quiet hours, and per-category error/success/mobile/desktop toggles.
 */
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import {
  AlertTriangle,
  CircleCheck,
  Smartphone,
  Monitor,
  Check,
  X,
  Moon,
  ChevronLeft,
  Save,
  RefreshCw,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { Spinner } from '../components/ui/Spinner';
import {
  getPreferences,
  updatePreferences,
  getDeliveryStatus,
  getCategoryIcon,
  getCategoryName,
  type NotificationPreferences,
  type NotificationCategory,
  type CategoryPreference,
  type DeliveryStatus,
} from '../api/notifications';
import { getMyNotificationRouting, type MyNotificationRouting } from '../api/notificationRouting';

const ALL_CATEGORIES: NotificationCategory[] = [
  'raid',
  'smart',
  'backup',
  'scheduler',
  'system',
  'security',
  'sync',
  'vpn',
];

const PRIORITY_LABELS = [
  { value: 0, label: 'priority.all', description: 'priority.allDesc' },
  { value: 1, label: 'priority.warnings', description: 'priority.warningsDesc' },
  { value: 2, label: 'priority.important', description: 'priority.importantDesc' },
  { value: 3, label: 'priority.critical', description: 'priority.criticalDesc' },
];

export default function NotificationPreferencesPage({ embedded = false }: { embedded?: boolean } = {}) {
  const { t } = useTranslation(['notifications', 'common']);
  const navigate = useNavigate();
  const { isAdmin: _isAdmin } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [_preferences, setPreferences] = useState<NotificationPreferences | null>(null);

  // Local state for form
  const [quietHoursEnabled, setQuietHoursEnabled] = useState(false);
  const [quietHoursStart, setQuietHoursStart] = useState('22:00');
  const [quietHoursEnd, setQuietHoursEnd] = useState('07:00');
  const [minPriority, setMinPriority] = useState(0);
  const [categoryPrefs, setCategoryPrefs] = useState<Record<string, CategoryPreference>>({});
  const [routing, setRouting] = useState<MyNotificationRouting | null>(null);
  const [deliveryStatus, setDeliveryStatus] = useState<DeliveryStatus>({ has_mobile_devices: false, has_desktop_clients: false });

  useEffect(() => {
    loadPreferences();
  }, []);

  useEffect(() => {
    getMyNotificationRouting()
      .then(setRouting)
      .catch(() => setRouting(null));
  }, []);

  useEffect(() => {
    getDeliveryStatus()
      .then(setDeliveryStatus)
      .catch(() => {});
  }, []);

  const loadPreferences = async () => {
    try {
      setLoading(true);
      const prefs = await getPreferences();
      setPreferences(prefs);

      // Populate form
      setQuietHoursEnabled(prefs.quiet_hours_enabled);
      setQuietHoursStart(prefs.quiet_hours_start || '22:00');
      setQuietHoursEnd(prefs.quiet_hours_end || '07:00');
      setMinPriority(prefs.min_priority);

      // Migrate old format if needed
      const rawPrefs = prefs.category_preferences || {};
      const migrated: Record<string, CategoryPreference> = {};
      for (const cat of ALL_CATEGORIES) {
        const pref = rawPrefs[cat];
        if (pref) {
          const p = pref as any;
          if ('push' in p && !('error' in p)) {
            // Old format: migrate
            migrated[cat] = {
              error: p.in_app ?? true,
              success: cat === 'backup',
              mobile: p.push ?? true,
              desktop: false,
            };
          } else {
            migrated[cat] = {
              error: p.error ?? true,
              success: p.success ?? (cat === 'backup'),
              mobile: p.mobile ?? true,
              desktop: p.desktop ?? false,
            };
          }
        }
      }
      setCategoryPrefs(migrated);
    } catch {
      toast.error(t('common:toast.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      await updatePreferences({
        quiet_hours_enabled: quietHoursEnabled,
        quiet_hours_start: quietHoursEnabled ? quietHoursStart : null,
        quiet_hours_end: quietHoursEnabled ? quietHoursEnd : null,
        min_priority: minPriority,
        category_preferences: categoryPrefs,
      });
      toast.success(t('common:toast.saved'));
    } catch {
      toast.error(t('common:toast.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const handleCategoryChange = (
    category: NotificationCategory,
    channel: keyof CategoryPreference,
    value: boolean
  ) => {
    setCategoryPrefs((prev) => {
      const existing = prev[category] || { error: true, success: category === 'backup', mobile: true, desktop: false };
      return {
        ...prev,
        [category]: {
          ...existing,
          [channel]: value,
        },
      };
    });
  };

  const getCategoryPref = (category: NotificationCategory): CategoryPreference => {
    return categoryPrefs[category] || { error: true, success: category === 'backup', mobile: true, desktop: false };
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      {embedded ? (
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-slate-400">
              {t('description')}
            </p>
          </div>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 rounded-xl border border-sky-500 bg-sky-500/10 px-4 py-2 text-sm font-medium text-sky-400 transition hover:bg-sky-500/20 disabled:opacity-50"
          >
            {saving ? (
              <RefreshCw className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {t('buttons.save')}
          </button>
        </div>
      ) : (
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate(-1)}
              className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 text-slate-400 transition hover:border-sky-500/50 hover:text-sky-400"
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
            <div>
              <h1 className="text-2xl font-bold text-slate-100">{t('title')}</h1>
              <p className="text-sm text-slate-400">
                {t('description')}
              </p>
            </div>
          </div>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 rounded-xl border border-sky-500 bg-sky-500/10 px-4 py-2 text-sm font-medium text-sky-400 transition hover:bg-sky-500/20 disabled:opacity-50"
          >
            {saving ? (
              <RefreshCw className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {t('buttons.save')}
          </button>
        </div>
      )}

      {/* Priority Filter */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <h2 className="mb-4 text-lg font-semibold text-slate-100">{t('priority.title')}</h2>
        <p className="mb-4 text-sm text-slate-400">
          {t('priority.description')}
        </p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {PRIORITY_LABELS.map(({ value, label, description }) => (
            <label
              key={value}
              className={`flex cursor-pointer flex-col rounded-lg border p-4 transition ${
                minPriority === value
                  ? 'border-sky-500 bg-sky-500/10'
                  : 'border-slate-800 hover:border-slate-700'
              }`}
            >
              <div className="flex items-center gap-2">
                <input
                  type="radio"
                  name="priority"
                  checked={minPriority === value}
                  onChange={() => setMinPriority(value)}
                  className="h-4 w-4 border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500/50"
                />
                <span className="font-medium text-slate-100">{t(label)}</span>
              </div>
              <p className="mt-1 pl-6 text-xs text-slate-400">{t(description)}</p>
            </label>
          ))}
        </div>
      </div>

      {/* Quiet Hours */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <Moon className="h-5 w-5 text-slate-400" />
            <div>
              <h2 className="text-lg font-semibold text-slate-100">{t('quietHours.title')}</h2>
              <p className="text-sm text-slate-400">{t('quietHours.description')}</p>
            </div>
          </div>
          <label className="relative inline-flex cursor-pointer items-center">
            <input
              type="checkbox"
              checked={quietHoursEnabled}
              onChange={(e) => setQuietHoursEnabled(e.target.checked)}
              className="peer sr-only"
            />
            <div className="peer h-6 w-11 rounded-full bg-slate-700 after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:border after:border-slate-600 after:bg-slate-400 after:transition-all after:content-[''] peer-checked:bg-sky-500 peer-checked:after:translate-x-full peer-checked:after:border-white peer-focus:outline-none" />
          </label>
        </div>

        {quietHoursEnabled && (
          <div className="flex items-center gap-4 mt-4">
            <div className="flex items-center gap-2">
              <label className="text-sm text-slate-400">{t('quietHours.from')}</label>
              <input
                type="time"
                value={quietHoursStart}
                onChange={(e) => setQuietHoursStart(e.target.value)}
                className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:border-sky-500 focus:outline-none"
              />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-sm text-slate-400">{t('quietHours.to')}</label>
              <input
                type="time"
                value={quietHoursEnd}
                onChange={(e) => setQuietHoursEnd(e.target.value)}
                className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:border-sky-500 focus:outline-none"
              />
            </div>
          </div>
        )}
      </div>

      {/* Admin-assigned routing (read-only) */}
      {routing && Object.values(routing).some((v) => v === true) && (
        <div className="border border-slate-700 rounded-lg p-4 mb-6">
          <h3 className="text-sm font-medium text-slate-300 mb-2">
            Zugewiesene System-Benachrichtigungen
          </h3>
          <p className="text-xs text-slate-500 mb-3">
            Diese Kategorien wurden dir von einem Administrator zugewiesen.
          </p>
          <div className="flex flex-wrap gap-2">
            {(Object.entries(routing) as [string, boolean][])
              .filter(([_, enabled]) => enabled)
              .map(([key]) => {
                const category = key.replace('receive_', '') as NotificationCategory;
                return (
                  <span
                    key={key}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-sky-500/10 text-sky-400 border border-sky-500/20"
                  >
                    {getCategoryName(category)}
                  </span>
                );
              })}
          </div>
        </div>
      )}

      {/* Category Settings */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <h2 className="mb-4 text-lg font-semibold text-slate-100">{t('categories.title')}</h2>
        <p className="mb-4 text-sm text-slate-400">
          {t('categories.description')}
        </p>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-800 text-left text-sm text-slate-400">
                <th className="pb-3 pr-4">{t('categories.type')}</th>
                <th className="pb-3 px-4 text-center">
                  <div className="flex items-center justify-center gap-1">
                    <AlertTriangle className="h-4 w-4 text-amber-400" />
                    <span>{t('categories.error')}</span>
                  </div>
                </th>
                <th className="pb-3 px-4 text-center">
                  <div className="flex items-center justify-center gap-1">
                    <CircleCheck className="h-4 w-4 text-emerald-400" />
                    <span>{t('categories.success')}</span>
                  </div>
                </th>
                <th className={`pb-3 px-4 text-center${!deliveryStatus.has_mobile_devices ? ' opacity-50' : ''}`}>
                  <div className="flex items-center justify-center gap-1">
                    <Smartphone className="h-4 w-4" />
                    <span>{t('categories.mobileApp')}</span>
                  </div>
                </th>
                <th className={`pb-3 pl-4 text-center${!deliveryStatus.has_desktop_clients ? ' opacity-50' : ''}`}>
                  <div className="flex items-center justify-center gap-1">
                    <Monitor className="h-4 w-4" />
                    <span>{t('categories.desktopClient')}</span>
                  </div>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {ALL_CATEGORIES.map((category) => {
                const pref = getCategoryPref(category);
                const isActive = pref.error || pref.success;
                return (
                  <tr key={category} className="text-sm">
                    <td className="py-3 pr-4">
                      <div className="flex items-center gap-2">
                        <span className="text-lg">{getCategoryIcon(category)}</span>
                        <span className="font-medium text-slate-100">
                          {getCategoryName(category)}
                        </span>
                        {isActive ? (
                          <Check className="h-4 w-4 text-emerald-400" />
                        ) : (
                          <X className="h-4 w-4 text-rose-400" />
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-4 text-center">
                      <input
                        type="checkbox"
                        checked={pref.error}
                        onChange={(e) =>
                          handleCategoryChange(category, 'error', e.target.checked)
                        }
                        className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500/50"
                      />
                    </td>
                    <td className="py-3 px-4 text-center">
                      <input
                        type="checkbox"
                        checked={pref.success}
                        onChange={(e) =>
                          handleCategoryChange(category, 'success', e.target.checked)
                        }
                        className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500/50"
                      />
                    </td>
                    <td className={`py-3 px-4 text-center${!deliveryStatus.has_mobile_devices ? ' opacity-50' : ''}`}>
                      <input
                        type="checkbox"
                        checked={pref.mobile}
                        onChange={(e) =>
                          handleCategoryChange(category, 'mobile', e.target.checked)
                        }
                        className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500/50"
                      />
                    </td>
                    <td className={`py-3 pl-4 text-center${!deliveryStatus.has_desktop_clients ? ' opacity-50' : ''}`}>
                      <input
                        type="checkbox"
                        checked={pref.desktop}
                        onChange={(e) =>
                          handleCategoryChange(category, 'desktop', e.target.checked)
                        }
                        className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500/50"
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
