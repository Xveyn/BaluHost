import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Layers, Plus, Pencil, Trash2, Play, Save, Shield } from 'lucide-react';
import toast from 'react-hot-toast';
import { useConfirmDialog } from '../../hooks/useConfirmDialog';
import type { FanCurveProfile, FanCurvePoint } from '../../api/fan-control';
import { createProfile, updateProfile, deleteProfile, applyProfileToFan } from '../../api/fan-control';
import ProfileForm from './ProfileForm';

interface ProfileManagerProps {
  profiles: FanCurveProfile[];
  selectedFanId: string | null;
  selectedFanCurve?: FanCurvePoint[];
  onProfilesChanged: () => void;
  onProfileApplied: () => void;
}

export default function ProfileManager({
  profiles,
  selectedFanId,
  selectedFanCurve,
  onProfilesChanged,
  onProfileApplied,
}: ProfileManagerProps) {
  const { t } = useTranslation(['system', 'common']);
  const { confirm, dialog } = useConfirmDialog();

  const [showForm, setShowForm] = useState(false);
  const [editingProfile, setEditingProfile] = useState<FanCurveProfile | undefined>();
  const [saveAsCurve, setSaveAsCurve] = useState<FanCurvePoint[] | undefined>();
  const [isSaving, setIsSaving] = useState(false);
  const [applyingId, setApplyingId] = useState<number | null>(null);

  const systemProfiles = profiles.filter(p => p.is_system);
  const userProfiles = profiles.filter(p => !p.is_system);

  const handleCreate = async (data: { name: string; description?: string; curve_points: FanCurvePoint[] }) => {
    setIsSaving(true);
    try {
      await createProfile(data);
      toast.success(t('system:fanControl.profiles.messages.created', { name: data.name }));
      setShowForm(false);
      setSaveAsCurve(undefined);
      onProfilesChanged();
    } catch {
      toast.error(t('system:fanControl.profiles.messages.createFailed'));
    } finally {
      setIsSaving(false);
    }
  };

  const handleUpdate = async (data: { name: string; description?: string; curve_points: FanCurvePoint[] }) => {
    if (!editingProfile) return;
    setIsSaving(true);
    try {
      await updateProfile(editingProfile.id, data);
      toast.success(t('system:fanControl.profiles.messages.updated'));
      setShowForm(false);
      setEditingProfile(undefined);
      onProfilesChanged();
    } catch {
      toast.error(t('system:fanControl.profiles.messages.updateFailed'));
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (profile: FanCurveProfile) => {
    const confirmed = await confirm(
      t('system:fanControl.profiles.deleteConfirmMessage', { name: profile.name }),
      { title: t('system:fanControl.profiles.deleteConfirmTitle'), variant: 'danger' }
    );
    if (!confirmed) return;
    try {
      await deleteProfile(profile.id);
      toast.success(t('system:fanControl.profiles.messages.deleted'));
      onProfilesChanged();
    } catch {
      toast.error(t('system:fanControl.profiles.messages.deleteFailed'));
    }
  };

  const handleApply = async (profile: FanCurveProfile) => {
    if (!selectedFanId) {
      toast.error(t('system:fanControl.profiles.noFanSelected'));
      return;
    }
    setApplyingId(profile.id);
    try {
      await applyProfileToFan(profile.id, selectedFanId);
      toast.success(t('system:fanControl.profiles.messages.applied', { name: profile.name }));
      onProfileApplied();
    } catch {
      toast.error(t('system:fanControl.profiles.messages.applyFailed'));
    } finally {
      setApplyingId(null);
    }
  };

  const handleSaveCurrentAsProfile = () => {
    setSaveAsCurve(selectedFanCurve);
    setEditingProfile(undefined);
    setShowForm(true);
  };

  const handleEdit = (profile: FanCurveProfile) => {
    setEditingProfile(profile);
    setSaveAsCurve(undefined);
    setShowForm(true);
  };

  const handleCancelForm = () => {
    setShowForm(false);
    setEditingProfile(undefined);
    setSaveAsCurve(undefined);
  };

  return (
    <div className="card">
      {dialog}

      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold text-white flex items-center gap-2">
          <Layers className="w-6 h-6 text-sky-400" />
          {t('system:fanControl.profiles.title')}
        </h2>
        <div className="flex gap-2">
          {selectedFanId && selectedFanCurve && selectedFanCurve.length >= 2 && (
            <button
              onClick={handleSaveCurrentAsProfile}
              className="px-3 py-1.5 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 text-sm flex items-center gap-1.5 transition-colors"
            >
              <Save className="w-4 h-4" />
              {t('system:fanControl.profiles.saveCurrentCurve')}
            </button>
          )}
          {userProfiles.length < 20 && (
            <button
              onClick={() => { setEditingProfile(undefined); setSaveAsCurve(undefined); setShowForm(true); }}
              className="px-3 py-1.5 bg-sky-500 text-white rounded-lg hover:bg-sky-600 shadow-lg shadow-sky-500/30 text-sm flex items-center gap-1.5 transition-colors"
            >
              <Plus className="w-4 h-4" />
              {t('system:fanControl.profiles.newProfile')}
            </button>
          )}
        </div>
      </div>

      <p className="text-sm text-slate-400 mb-4">
        {t('system:fanControl.profiles.description')}
      </p>

      {/* Inline Form */}
      {showForm && (
        <div className="mb-4">
          <ProfileForm
            profile={editingProfile}
            initialCurvePoints={saveAsCurve}
            onSave={editingProfile ? handleUpdate : handleCreate}
            onCancel={handleCancelForm}
            isSaving={isSaving}
          />
        </div>
      )}

      {/* System Profiles */}
      {systemProfiles.length > 0 && (
        <div className="mb-4">
          <h3 className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
            {t('system:fanControl.profiles.systemProfiles')}
          </h3>
          <div className="space-y-2">
            {systemProfiles.map(profile => (
              <div key={profile.id} className="flex items-center justify-between px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg">
                <div className="flex items-center gap-2 min-w-0">
                  <Shield className="w-4 h-4 text-violet-400 flex-shrink-0" />
                  <span className="text-sm font-medium text-white truncate">{profile.name}</span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-violet-500/20 text-violet-300 border border-violet-500/30 flex-shrink-0">
                    System
                  </span>
                  {profile.description && (
                    <span className="text-xs text-slate-500 truncate hidden sm:inline">{profile.description}</span>
                  )}
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  <button
                    onClick={() => handleEdit(profile)}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-sky-400 hover:bg-slate-700 transition-colors"
                    title={t('system:fanControl.profiles.editCurve')}
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleApply(profile)}
                    disabled={!selectedFanId || applyingId === profile.id}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-emerald-400 hover:bg-slate-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    title={t('system:fanControl.profiles.apply')}
                  >
                    {applyingId === profile.id ? (
                      <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-400 border-t-transparent" />
                    ) : (
                      <Play className="w-4 h-4" />
                    )}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* User Profiles */}
      {userProfiles.length > 0 && (
        <div>
          <h3 className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
            {t('system:fanControl.profiles.customProfiles')} ({userProfiles.length}/20)
          </h3>
          <div className="space-y-2">
            {userProfiles.map(profile => (
              <div key={profile.id} className="flex items-center justify-between px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-sm font-medium text-white truncate">{profile.name}</span>
                  {profile.description && (
                    <span className="text-xs text-slate-500 truncate hidden sm:inline">{profile.description}</span>
                  )}
                  <span className="text-[10px] text-slate-500 flex-shrink-0">{profile.curve_points.length} pts</span>
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  <button
                    onClick={() => handleApply(profile)}
                    disabled={!selectedFanId || applyingId === profile.id}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-emerald-400 hover:bg-slate-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    title={t('system:fanControl.profiles.apply')}
                  >
                    {applyingId === profile.id ? (
                      <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-400 border-t-transparent" />
                    ) : (
                      <Play className="w-4 h-4" />
                    )}
                  </button>
                  <button
                    onClick={() => handleEdit(profile)}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-sky-400 hover:bg-slate-700 transition-colors"
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleDelete(profile)}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-700 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {profiles.length === 0 && !showForm && (
        <div className="text-center py-6">
          <Layers className="w-10 h-10 mx-auto text-slate-600 mb-2" />
          <p className="text-sm text-slate-400">{t('system:fanControl.profiles.noProfiles')}</p>
        </div>
      )}
    </div>
  );
}
