import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Server, RefreshCw, AlertCircle, Loader2, Plus, Pencil, Trash2 } from 'lucide-react';
import toast from 'react-hot-toast';
import {
  getNfsStatus, listNfsExports, createNfsExport, updateNfsExport, deleteNfsExport,
  type NfsStatus, type NfsExport, type NfsExportInput,
} from '../../api/nfs';

const EMPTY_FORM: NfsExportInput = {
  path: '', clients: '', read_only: false, root_squash: true, enabled: true, comment: null,
};

export default function NfsManagementCard() {
  const { t } = useTranslation('system');
  const [status, setStatus] = useState<NfsStatus | null>(null);
  const [exports, setExports] = useState<NfsExport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<NfsExport | null>(null);
  const [form, setForm] = useState<NfsExportInput>(EMPTY_FORM);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [s, e] = await Promise.all([getNfsStatus(), listNfsExports()]);
      setStatus(s);
      setExports(e);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const openAdd = () => { setEditing(null); setForm(EMPTY_FORM); setShowForm(true); };
  const openEdit = (exp: NfsExport) => {
    setEditing(exp);
    setForm({
      path: exp.path, clients: exp.clients, read_only: exp.read_only,
      root_squash: exp.root_squash, enabled: exp.enabled, comment: exp.comment,
    });
    setShowForm(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (editing) {
        await updateNfsExport(editing.id, form);
        toast.success(t('nfs.updated'));
      } else {
        await createNfsExport(form);
        toast.success(t('nfs.created'));
      }
      setShowForm(false);
      await loadData();
    } catch {
      toast.error(t(editing ? 'nfs.updateFailed' : 'nfs.createFailed'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (exp: NfsExport) => {
    if (!window.confirm(t('nfs.deleteConfirm'))) return;
    try {
      await deleteNfsExport(exp.id);
      toast.success(t('nfs.deleted'));
      await loadData();
    } catch {
      toast.error(t('nfs.deleteFailed'));
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-slate-400">
        <Loader2 className="h-5 w-5 animate-spin mr-2" />
        {t('nfs.loading')}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 rounded-lg bg-red-500/10 border border-red-500/20 p-4 text-red-400">
        <AlertCircle className="h-5 w-5 shrink-0" />
        <span>{error}</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <Server className="h-6 w-6 text-blue-400" />
            {t('nfs.title')}
          </h2>
          <p className="mt-1 text-sm text-slate-400">{t('nfs.subtitle')}</p>
        </div>
        <button
          onClick={loadData}
          className="flex items-center gap-1.5 rounded-lg bg-slate-800/50 px-3 py-2 text-sm text-slate-400 hover:text-white hover:bg-slate-700/50 transition-colors"
        >
          <RefreshCw className="h-4 w-4" />
          {t('nfs.refresh')}
        </button>
      </div>

      {status && (
        <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-5 flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <div className={`h-2.5 w-2.5 rounded-full ${status.is_running ? 'bg-green-400' : 'bg-red-400'}`} />
            <span className={`text-sm font-medium ${status.is_running ? 'text-green-400' : 'text-red-400'}`}>
              {status.is_running ? t('nfs.running') : t('nfs.notRunning')}
            </span>
          </div>
          <div className="text-sm text-slate-400">{t('nfs.exportsCount')}: {status.exports_count}</div>
        </div>
      )}

      {status && !status.is_running && (
        <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 p-4 text-amber-300 text-sm">
          <AlertCircle className="h-4 w-4 inline mr-2" />
          {t('nfs.notRunningHint')}
        </div>
      )}

      <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 p-4 text-amber-300 text-sm">
        <AlertCircle className="h-4 w-4 inline mr-2" />
        {t('nfs.lanWarning')}
      </div>

      <div>
        <div className="flex items-center justify-end mb-3">
          <button
            onClick={openAdd}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
          >
            <Plus className="h-4 w-4" />
            {t('nfs.addExport')}
          </button>
        </div>

        {exports.length === 0 ? (
          <p className="text-sm text-slate-500">{t('nfs.noExports')}</p>
        ) : (
          <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-700/50 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">
                  <th className="px-4 py-3">{t('nfs.path')}</th>
                  <th className="px-4 py-3">{t('nfs.clients')}</th>
                  <th className="px-4 py-3">{t('nfs.mode')}</th>
                  <th className="px-4 py-3">{t('nfs.squash')}</th>
                  <th className="px-4 py-3">{t('nfs.enabledLabel')}</th>
                  <th className="px-4 py-3 text-right">{t('nfs.actions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/30">
                {exports.map((exp) => (
                  <tr key={exp.id} className="hover:bg-slate-800/30 transition-colors text-sm">
                    <td className="px-4 py-3 text-white font-medium">
                      <div>{exp.path || <span className="text-slate-500">{t('nfs.wholeRoot')}</span>}</div>
                      <code className="mt-1 block text-[11px] font-mono text-slate-500 break-all">{exp.mount_target}</code>
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-300">{exp.clients}</td>
                    <td className="px-4 py-3 text-slate-300">
                      {exp.read_only ? t('nfs.readOnly') : t('nfs.readWrite')}
                    </td>
                    <td className="px-4 py-3 text-slate-300">{exp.root_squash ? t('nfs.on') : t('nfs.off')}</td>
                    <td className="px-4 py-3 text-slate-300">{exp.enabled ? t('nfs.on') : t('nfs.off')}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2">
                        <button onClick={() => openEdit(exp)} className="text-slate-400 hover:text-white" title={t('nfs.edit')}>
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button onClick={() => handleDelete(exp)} className="text-red-400 hover:text-red-300" title={t('nfs.delete')}>
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl bg-slate-900 border border-slate-700/50 p-6 shadow-2xl space-y-4">
            <h3 className="text-lg font-semibold text-white">
              {editing ? t('nfs.editTitle') : t('nfs.addTitle')}
            </h3>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">{t('nfs.path')}</label>
              <input
                type="text" value={form.path}
                onChange={(e) => setForm({ ...form, path: e.target.value })}
                placeholder={t('nfs.pathPlaceholder')}
                className="w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-blue-500 outline-none"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">{t('nfs.clients')}</label>
              <input
                type="text" value={form.clients}
                onChange={(e) => setForm({ ...form, clients: e.target.value })}
                placeholder={t('nfs.clientsPlaceholder')}
                className="w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-blue-500 outline-none"
              />
            </div>

            <div className="flex flex-wrap gap-4">
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input type="checkbox" checked={form.read_only}
                  onChange={(e) => setForm({ ...form, read_only: e.target.checked })} />
                {t('nfs.readOnly')}
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input type="checkbox" checked={form.root_squash}
                  onChange={(e) => setForm({ ...form, root_squash: e.target.checked })} />
                {t('nfs.squash')}
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input type="checkbox" checked={form.enabled}
                  onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
                {t('nfs.enabledLabel')}
              </label>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button onClick={() => setShowForm(false)}
                className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:text-white hover:bg-slate-800 transition-colors">
                {t('nfs.cancel')}
              </button>
              <button onClick={handleSave} disabled={saving}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50 transition-colors">
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : (editing ? t('nfs.save') : t('nfs.create'))}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
