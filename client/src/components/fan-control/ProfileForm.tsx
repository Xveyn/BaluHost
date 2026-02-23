import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import type { FanCurveProfile, FanCurvePoint } from '../../api/fan-control';

interface ProfileFormProps {
  profile?: FanCurveProfile;
  initialCurvePoints?: FanCurvePoint[];
  onSave: (data: { name: string; description?: string; curve_points: FanCurvePoint[] }) => Promise<void>;
  onCancel: () => void;
  isSaving: boolean;
}

export default function ProfileForm({ profile, initialCurvePoints, onSave, onCancel, isSaving }: ProfileFormProps) {
  const { t } = useTranslation(['system', 'common']);
  const isEditing = !!profile;

  const [name, setName] = useState(profile?.name ?? '');
  const [description, setDescription] = useState(profile?.description ?? '');
  const [curvePoints, setCurvePoints] = useState<FanCurvePoint[]>(
    profile?.curve_points ?? initialCurvePoints ?? [
      { temp: 35, pwm: 30 },
      { temp: 50, pwm: 50 },
      { temp: 70, pwm: 80 },
      { temp: 85, pwm: 100 },
    ]
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    await onSave({
      name: name.trim(),
      description: description.trim() || undefined,
      curve_points: curvePoints,
    });
  };

  return (
    <div className="border border-slate-700 rounded-lg bg-slate-800/50 p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white">
          {isEditing ? t('system:fanControl.profiles.editProfile') : t('system:fanControl.profiles.newProfile')}
        </h3>
        <button onClick={onCancel} className="p-1 text-slate-400 hover:text-slate-300 transition-colors">
          <X className="w-4 h-4" />
        </button>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs text-slate-400 mb-1">
            {t('system:fanControl.profiles.name')}
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t('system:fanControl.profiles.namePlaceholder')}
            className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white text-sm focus:outline-none focus:border-sky-500"
            maxLength={100}
            required
            disabled={isEditing && profile?.is_system}
          />
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1">
            {t('system:fanControl.profiles.description')}
          </label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder={t('system:fanControl.profiles.descriptionPlaceholder')}
            className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white text-sm focus:outline-none focus:border-sky-500"
            maxLength={255}
          />
        </div>

        {/* Curve Editor Table */}
        <div>
          <label className="block text-xs text-slate-400 mb-1">
            {t('system:fanControl.profiles.curvePoints')}
          </label>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border border-slate-700 rounded">
              <thead className="bg-slate-900">
                <tr>
                  <th className="px-3 py-1.5 text-left text-xs text-slate-400">Temp (&deg;C)</th>
                  <th className="px-3 py-1.5 text-left text-xs text-slate-400">PWM (%)</th>
                  <th className="px-3 py-1.5 text-left text-xs text-slate-400"></th>
                </tr>
              </thead>
              <tbody>
                {curvePoints.map((point, i) => (
                  <tr key={i} className="border-t border-slate-700">
                    <td className="px-3 py-1.5">
                      <input
                        type="number"
                        value={point.temp}
                        onChange={(e) => {
                          const updated = [...curvePoints];
                          updated[i] = { ...updated[i], temp: parseFloat(e.target.value) || 0 };
                          setCurvePoints(updated);
                        }}
                        className="w-16 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-white text-xs"
                        min={0}
                        max={150}
                      />
                    </td>
                    <td className="px-3 py-1.5">
                      <input
                        type="number"
                        value={point.pwm}
                        onChange={(e) => {
                          const updated = [...curvePoints];
                          updated[i] = { ...updated[i], pwm: parseInt(e.target.value) || 0 };
                          setCurvePoints(updated);
                        }}
                        className="w-16 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-white text-xs"
                        min={0}
                        max={100}
                      />
                    </td>
                    <td className="px-3 py-1.5">
                      {curvePoints.length > 2 && (
                        <button
                          type="button"
                          onClick={() => setCurvePoints(curvePoints.filter((_, j) => j !== i))}
                          className="text-rose-400 hover:text-rose-300 text-xs"
                        >
                          &times;
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {curvePoints.length < 10 && (
              <button
                type="button"
                onClick={() => {
                  const last = curvePoints[curvePoints.length - 1];
                  setCurvePoints([...curvePoints, {
                    temp: (last?.temp ?? 50) + 10,
                    pwm: Math.min((last?.pwm ?? 50) + 15, 100),
                  }]);
                }}
                className="mt-2 px-3 py-1 bg-slate-700 text-slate-300 rounded text-xs hover:bg-slate-600"
              >
                + {t('system:fanControl.curve.addPoint')}
              </button>
            )}
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-2 border-t border-slate-700">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 text-sm"
            disabled={isSaving}
          >
            {t('common:cancel')}
          </button>
          <button
            type="submit"
            disabled={!name.trim() || curvePoints.length < 2 || isSaving}
            className="px-4 py-2 bg-sky-500 text-white rounded-lg hover:bg-sky-600 shadow-lg shadow-sky-500/30 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving ? (
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
            ) : isEditing ? (
              t('system:fanControl.profiles.update')
            ) : (
              t('system:fanControl.profiles.create')
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
