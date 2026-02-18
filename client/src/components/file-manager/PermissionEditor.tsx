/**
 * PermissionEditor component -- modal for editing file permission rules.
 */

import { X, Trash2, Plus } from 'lucide-react';
import type { FileItem, PermissionRule } from './types';

interface PermissionEditorProps {
  file: FileItem;
  rules: PermissionRule[];
  allUsers: Array<{ id: string; username: string }>;
  onRulesChange: (rules: PermissionRule[]) => void;
  onSave: () => void;
  onClose: () => void;
}

export function PermissionEditor({ rules, allUsers, onRulesChange, onSave, onClose }: PermissionEditorProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 backdrop-blur-xl p-4">
      <div className="card w-full max-w-xl max-h-[85vh] flex flex-col border-indigo-500/30 bg-slate-900/80 backdrop-blur-2xl shadow-[0_20px_70px_rgba(0,0,0,0.5)]">
        <div className="flex-shrink-0 flex items-center justify-between pb-4 border-b border-slate-800/60">
          <div>
            <h3 className="text-lg font-semibold text-white">Rechte bearbeiten</h3>
            <p className="mt-0.5 text-xs text-slate-400">Lege für jeden Nutzer eine Berechtigungsregel fest.</p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="mt-5 space-y-4 flex-1 overflow-y-auto min-h-0">
          {rules.length > 0 && rules.map((rule, idx) => (
            <div key={idx} className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 border-b border-slate-800/40 pb-4 mb-4">
              <select
                value={rule.userId}
                onChange={e => {
                  const newRules = [...rules];
                  newRules[idx].userId = e.target.value;
                  onRulesChange(newRules);
                }}
                className="input w-full sm:w-48"
              >
                <option value="">Nutzer wählen...</option>
                {allUsers.map(u => (
                  <option key={u.id} value={u.id}>{u.username}</option>
                ))}
              </select>
              <div className="flex flex-wrap items-center gap-3 sm:gap-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={rule.canView}
                    onChange={e => {
                      const newRules = [...rules];
                      newRules[idx].canView = e.target.checked;
                      onRulesChange(newRules);
                    }}
                    className="h-4 w-4 rounded border-slate-600 bg-slate-800/50 text-indigo-500 focus:ring-indigo-500 focus:ring-offset-0 cursor-pointer"
                  />
                  <span className="text-xs sm:text-sm text-slate-300">Sehen</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={rule.canEdit}
                    onChange={e => {
                      const newRules = [...rules];
                      newRules[idx].canEdit = e.target.checked;
                      onRulesChange(newRules);
                    }}
                    className="h-4 w-4 rounded border-slate-600 bg-slate-800/50 text-indigo-500 focus:ring-indigo-500 focus:ring-offset-0 cursor-pointer"
                  />
                  <span className="text-xs sm:text-sm text-slate-300">Bearbeiten</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={rule.canDelete}
                    onChange={e => {
                      const newRules = [...rules];
                      newRules[idx].canDelete = e.target.checked;
                      onRulesChange(newRules);
                    }}
                    className="h-4 w-4 rounded border-slate-600 bg-slate-800/50 text-indigo-500 focus:ring-indigo-500 focus:ring-offset-0 cursor-pointer"
                  />
                  <span className="text-xs sm:text-sm text-slate-300">Löschen</span>
                </label>
                <button
                  onClick={() => {
                    onRulesChange(rules.filter((_, i) => i !== idx));
                  }}
                  className="p-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-200 hover:border-rose-500/50 hover:bg-rose-500/20 transition-colors"
                  title="Entfernen"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
          <button
            onClick={() => onRulesChange([...rules, { userId: '', canView: true, canEdit: false, canDelete: false }])}
            className="flex items-center gap-2 rounded-xl border border-indigo-500/40 bg-indigo-500/10 px-4 py-2 text-sm font-medium text-indigo-200 transition hover:border-indigo-400/60 hover:bg-indigo-500/20"
          >
            <Plus className="w-4 h-4" />
            Regel hinzufügen
          </button>
        </div>
        <div className="flex justify-end gap-3 pt-5 mt-5 border-t border-slate-800/40 flex-shrink-0">
          <button
            onClick={onClose}
            className="rounded-xl border border-slate-700/70 bg-slate-900/70 px-4 py-2 text-sm font-medium text-slate-300 transition hover:border-slate-500 hover:text-white"
          >
            Abbrechen
          </button>
          <button
            onClick={onSave}
            className="btn btn-primary"
          >
            Speichern
          </button>
        </div>
      </div>
    </div>
  );
}
