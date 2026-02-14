/**
 * PermissionEditor component -- modal for editing file permission rules.
 */

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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-lg p-4">
      <div className="card w-full max-w-xl max-h-[85vh] flex flex-col border-indigo-500/30 bg-slate-900/80">
        <div className="flex-shrink-0">
          <h3 className="text-xl font-semibold text-white">Rechte bearbeiten</h3>
          <p className="mt-2 text-sm text-slate-400">Lege für jeden Nutzer eine Berechtigungsregel fest.</p>
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
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={rule.canView}
                    onChange={e => {
                      const newRules = [...rules];
                      newRules[idx].canView = e.target.checked;
                      onRulesChange(newRules);
                    }}
                    className="mr-2"
                  />
                  <span className="text-sm">Sehen</span>
                </label>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={rule.canEdit}
                    onChange={e => {
                      const newRules = [...rules];
                      newRules[idx].canEdit = e.target.checked;
                      onRulesChange(newRules);
                    }}
                    className="mr-2"
                  />
                  <span className="text-sm">Bearbeiten</span>
                </label>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={rule.canDelete}
                    onChange={e => {
                      const newRules = [...rules];
                      newRules[idx].canDelete = e.target.checked;
                      onRulesChange(newRules);
                    }}
                    className="mr-2"
                  />
                  <span className="text-sm">Löschen</span>
                </label>
                <button
                  onClick={() => {
                    onRulesChange(rules.filter((_, i) => i !== idx));
                  }}
                  className="ml-2 px-2 py-1 text-xs rounded bg-rose-900/40 text-rose-300 hover:bg-rose-900/60"
                >
                  Entfernen
                </button>
              </div>
            </div>
          ))}
          <button
            onClick={() => onRulesChange([...rules, { userId: '', canView: true, canEdit: false, canDelete: false }])}
            className="rounded-xl border border-indigo-500/40 bg-indigo-500/10 px-4 py-2 text-sm font-medium text-indigo-200 transition hover:border-indigo-400/60 hover:bg-indigo-500/20"
          >
            + Regel hinzufügen
          </button>
        </div>
        <div className="mt-6 flex justify-end gap-3 flex-shrink-0">
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
