/**
 * Notification Preferences Page
 *
 * Allows users to configure their notification settings including
 * channel preferences, category filters, and quiet hours.
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Mail,
  Smartphone,
  Monitor,
  Moon,
  ChevronLeft,
  Save,
  RefreshCw,
} from 'lucide-react';
import toast from 'react-hot-toast';
import {
  getPreferences,
  updatePreferences,
  getCategoryIcon,
  getCategoryName,
  type NotificationPreferences,
  type NotificationCategory,
  type CategoryPreference,
} from '../api/notifications';

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
  { value: 0, label: 'Alle', description: 'Alle Benachrichtigungen erhalten' },
  { value: 1, label: 'Warnungen+', description: 'Nur Warnungen und kritische Meldungen' },
  { value: 2, label: 'Wichtig', description: 'Nur hohe Priorität und kritische Meldungen' },
  { value: 3, label: 'Nur kritisch', description: 'Nur kritische Systemmeldungen' },
];

export default function NotificationPreferencesPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [_preferences, setPreferences] = useState<NotificationPreferences | null>(null);

  // Local state for form
  const [emailEnabled, setEmailEnabled] = useState(true);
  const [pushEnabled, setPushEnabled] = useState(true);
  const [inAppEnabled, setInAppEnabled] = useState(true);
  const [quietHoursEnabled, setQuietHoursEnabled] = useState(false);
  const [quietHoursStart, setQuietHoursStart] = useState('22:00');
  const [quietHoursEnd, setQuietHoursEnd] = useState('07:00');
  const [minPriority, setMinPriority] = useState(0);
  const [categoryPrefs, setCategoryPrefs] = useState<Record<string, CategoryPreference>>({});

  useEffect(() => {
    loadPreferences();
  }, []);

  const loadPreferences = async () => {
    try {
      setLoading(true);
      const prefs = await getPreferences();
      setPreferences(prefs);

      // Populate form
      setEmailEnabled(prefs.email_enabled);
      setPushEnabled(prefs.push_enabled);
      setInAppEnabled(prefs.in_app_enabled);
      setQuietHoursEnabled(prefs.quiet_hours_enabled);
      setQuietHoursStart(prefs.quiet_hours_start || '22:00');
      setQuietHoursEnd(prefs.quiet_hours_end || '07:00');
      setMinPriority(prefs.min_priority);
      setCategoryPrefs(prefs.category_preferences || {});
    } catch (error) {
      console.error('Failed to load preferences:', error);
      toast.error('Fehler beim Laden der Einstellungen');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      await updatePreferences({
        email_enabled: emailEnabled,
        push_enabled: pushEnabled,
        in_app_enabled: inAppEnabled,
        quiet_hours_enabled: quietHoursEnabled,
        quiet_hours_start: quietHoursEnabled ? quietHoursStart : null,
        quiet_hours_end: quietHoursEnabled ? quietHoursEnd : null,
        min_priority: minPriority,
        category_preferences: categoryPrefs,
      });
      toast.success('Einstellungen gespeichert');
    } catch (error) {
      console.error('Failed to save preferences:', error);
      toast.error('Fehler beim Speichern');
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
      const existing = prev[category] || { email: true, push: true, in_app: true };
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
    return categoryPrefs[category] || { email: true, push: true, in_app: true };
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-sky-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate(-1)}
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 text-slate-400 transition hover:border-sky-500/50 hover:text-sky-400"
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-slate-100">Benachrichtigungen</h1>
            <p className="text-sm text-slate-400">
              Konfiguriere wie und wann du benachrichtigt wirst
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
          Speichern
        </button>
      </div>

      {/* Global Channel Settings */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <h2 className="mb-4 text-lg font-semibold text-slate-100">Benachrichtigungskanäle</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          {/* Email */}
          <label className="flex cursor-pointer items-center gap-3 rounded-lg border border-slate-800 p-4 transition hover:border-slate-700">
            <input
              type="checkbox"
              checked={emailEnabled}
              onChange={(e) => setEmailEnabled(e.target.checked)}
              className="h-5 w-5 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500/50"
            />
            <div className="flex items-center gap-3">
              <Mail className="h-5 w-5 text-slate-400" />
              <div>
                <p className="font-medium text-slate-100">E-Mail</p>
                <p className="text-xs text-slate-400">Benachrichtigungen per E-Mail</p>
              </div>
            </div>
          </label>

          {/* Push */}
          <label className="flex cursor-pointer items-center gap-3 rounded-lg border border-slate-800 p-4 transition hover:border-slate-700">
            <input
              type="checkbox"
              checked={pushEnabled}
              onChange={(e) => setPushEnabled(e.target.checked)}
              className="h-5 w-5 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500/50"
            />
            <div className="flex items-center gap-3">
              <Smartphone className="h-5 w-5 text-slate-400" />
              <div>
                <p className="font-medium text-slate-100">Push</p>
                <p className="text-xs text-slate-400">Mobile App Benachrichtigungen</p>
              </div>
            </div>
          </label>

          {/* In-App */}
          <label className="flex cursor-pointer items-center gap-3 rounded-lg border border-slate-800 p-4 transition hover:border-slate-700">
            <input
              type="checkbox"
              checked={inAppEnabled}
              onChange={(e) => setInAppEnabled(e.target.checked)}
              className="h-5 w-5 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500/50"
            />
            <div className="flex items-center gap-3">
              <Monitor className="h-5 w-5 text-slate-400" />
              <div>
                <p className="font-medium text-slate-100">In-App</p>
                <p className="text-xs text-slate-400">Benachrichtigungen im Browser</p>
              </div>
            </div>
          </label>
        </div>
      </div>

      {/* Priority Filter */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <h2 className="mb-4 text-lg font-semibold text-slate-100">Prioritätsfilter</h2>
        <p className="mb-4 text-sm text-slate-400">
          Wähle die minimale Priorität für Benachrichtigungen
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
                <span className="font-medium text-slate-100">{label}</span>
              </div>
              <p className="mt-1 pl-6 text-xs text-slate-400">{description}</p>
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
              <h2 className="text-lg font-semibold text-slate-100">Ruhezeiten</h2>
              <p className="text-sm text-slate-400">Keine Benachrichtigungen während dieser Zeit</p>
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
              <label className="text-sm text-slate-400">Von</label>
              <input
                type="time"
                value={quietHoursStart}
                onChange={(e) => setQuietHoursStart(e.target.value)}
                className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:border-sky-500 focus:outline-none"
              />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-sm text-slate-400">Bis</label>
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

      {/* Category Settings */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <h2 className="mb-4 text-lg font-semibold text-slate-100">Kategorie-Einstellungen</h2>
        <p className="mb-4 text-sm text-slate-400">
          Konfiguriere Benachrichtigungen für einzelne Kategorien
        </p>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-800 text-left text-sm text-slate-400">
                <th className="pb-3 pr-4">Kategorie</th>
                <th className="pb-3 px-4 text-center">
                  <div className="flex items-center justify-center gap-1">
                    <Mail className="h-4 w-4" />
                    <span>E-Mail</span>
                  </div>
                </th>
                <th className="pb-3 px-4 text-center">
                  <div className="flex items-center justify-center gap-1">
                    <Smartphone className="h-4 w-4" />
                    <span>Push</span>
                  </div>
                </th>
                <th className="pb-3 pl-4 text-center">
                  <div className="flex items-center justify-center gap-1">
                    <Monitor className="h-4 w-4" />
                    <span>In-App</span>
                  </div>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {ALL_CATEGORIES.map((category) => {
                const pref = getCategoryPref(category);
                return (
                  <tr key={category} className="text-sm">
                    <td className="py-3 pr-4">
                      <div className="flex items-center gap-2">
                        <span className="text-lg">{getCategoryIcon(category)}</span>
                        <span className="font-medium text-slate-100">
                          {getCategoryName(category)}
                        </span>
                      </div>
                    </td>
                    <td className="py-3 px-4 text-center">
                      <input
                        type="checkbox"
                        checked={pref.email && emailEnabled}
                        disabled={!emailEnabled}
                        onChange={(e) =>
                          handleCategoryChange(category, 'email', e.target.checked)
                        }
                        className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500/50 disabled:opacity-50"
                      />
                    </td>
                    <td className="py-3 px-4 text-center">
                      <input
                        type="checkbox"
                        checked={pref.push && pushEnabled}
                        disabled={!pushEnabled}
                        onChange={(e) =>
                          handleCategoryChange(category, 'push', e.target.checked)
                        }
                        className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500/50 disabled:opacity-50"
                      />
                    </td>
                    <td className="py-3 pl-4 text-center">
                      <input
                        type="checkbox"
                        checked={pref.in_app && inAppEnabled}
                        disabled={!inAppEnabled}
                        onChange={(e) =>
                          handleCategoryChange(category, 'in_app', e.target.checked)
                        }
                        className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500/50 disabled:opacity-50"
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
