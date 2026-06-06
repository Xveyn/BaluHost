import {
  Download,
  CheckCircle,
  AlertTriangle,
  GitBranch,
  Clock,
  Loader2,
  Zap,
  FileText,
  Package,
} from 'lucide-react';
import Markdown from 'react-markdown';
import type { UpdateCheckResponse, ReleaseNotesResponse } from '../../api/updates';
import { isUpdateInProgress, type UpdateProgressResponse } from '../../api/updates';
import UpdateProgress from './UpdateProgress';

const PROSE =
  'prose prose-invert prose-slate max-w-none prose-sm ' +
  'prose-headings:text-white prose-h2:text-base prose-h3:text-sm ' +
  'prose-p:text-slate-300 prose-li:text-slate-300 prose-strong:text-white ' +
  'prose-a:text-blue-400 prose-code:text-cyan-400';

interface UpdateOverviewTabProps {
  t: (key: string, options?: Record<string, unknown>) => string;
  checkResult: UpdateCheckResponse | null;
  currentUpdate: UpdateProgressResponse | null;
  releaseNotes: ReleaseNotesResponse | null;
  updateLoading: boolean;
  rollbackLoading: boolean;
  cancelLoading: boolean;
  showUpdateConfirm: boolean;
  onSetShowUpdateConfirm: (show: boolean) => void;
  onSetShowRollbackConfirm: (show: boolean) => void;
  onStartUpdate: () => void;
  onCancel: () => void;
}

export default function UpdateOverviewTab({
  t,
  checkResult,
  currentUpdate,
  releaseNotes,
  updateLoading,
  rollbackLoading,
  cancelLoading,
  showUpdateConfirm,
  onSetShowUpdateConfirm,
  onSetShowRollbackConfirm,
  onStartUpdate,
  onCancel,
}: UpdateOverviewTabProps) {
  return (
    <div className="space-y-6">
      {/* Current Update Progress */}
      {currentUpdate && isUpdateInProgress(currentUpdate.status) && (
        <UpdateProgress
          progress={currentUpdate}
          onRollback={() => onSetShowRollbackConfirm(true)}
          rollbackLoading={rollbackLoading}
          onCancel={onCancel}
          cancelLoading={cancelLoading}
        />
      )}

      {/* Version Info Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Current Version */}
        <div className="bg-slate-800 rounded-lg p-5 border border-slate-700">
          <div className="flex items-center gap-2 mb-4">
            <Package className="h-5 w-5 text-slate-400" />
            <h3 className="font-medium text-white">{t('version.current')}</h3>
          </div>
          {checkResult && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-3xl font-bold text-white">
                  v{checkResult.current_version.version}
                </span>
                {checkResult.current_version.is_prerelease && (
                  <span className="ml-2 inline-flex items-center rounded-md bg-amber-500/20 px-2 py-0.5 text-xs font-medium text-amber-300">
                    {t('preRelease.badge')}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <GitBranch className="h-4 w-4" />
                <span className="font-mono">{checkResult.current_version.commit_short}</span>
                {checkResult.current_version.tag && (
                  <span className="px-2 py-0.5 bg-slate-700 rounded text-xs">
                    {checkResult.current_version.tag}
                  </span>
                )}
              </div>
              {checkResult.current_version.is_dev_build ? (
                <div className="flex items-center gap-2 text-sm">
                  <span className="px-2 py-0.5 bg-amber-500/20 text-amber-400 rounded text-xs font-medium">
                    {t('version.devBuild')}
                  </span>
                </div>
              ) : !checkResult.current_version.is_prerelease ? (
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-emerald-400">{t('version.stable')}</span>
                </div>
              ) : null}
            </div>
          )}
        </div>

        {/* Available Update */}
        <div
          className={`bg-slate-800 rounded-lg p-5 border ${
            checkResult?.update_available ? 'border-blue-500/50 bg-blue-500/5' : 'border-slate-700'
          }`}
        >
          <div className="flex items-center gap-2 mb-4">
            {checkResult?.update_available ? (
              <Zap className="h-5 w-5 text-blue-400" />
            ) : (
              <CheckCircle className="h-5 w-5 text-emerald-400" />
            )}
            <h3 className="font-medium text-white">
              {checkResult?.update_available ? t('version.available') : t('version.upToDate')}
            </h3>
          </div>
          {checkResult?.update_available && checkResult.latest_version ? (
            <div className="space-y-3">
              <div className="text-3xl font-bold text-blue-400">
                v{checkResult.latest_version.version}
              </div>
              {checkResult.last_checked && (
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <Clock className="h-3 w-3" />
                  {t('version.lastChecked')} {new Date(checkResult.last_checked).toLocaleString()}
                </div>
              )}
            </div>
          ) : (
            <p className="text-slate-400">{t('version.upToDateDesc')}</p>
          )}
        </div>
      </div>

      {/* Blockers Warning */}
      {checkResult?.blockers && checkResult.blockers.length > 0 && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-400 mt-0.5" />
            <div>
              <h4 className="font-medium text-amber-400">{t('blockers.title')}</h4>
              <ul className="mt-2 space-y-1 text-sm text-slate-300">
                {checkResult.blockers.map((blocker, i) => (
                  <li key={i}>• {blocker}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Release Notes (markdown, since last stable) */}
      {releaseNotes && releaseNotes.releases.length > 0 && (
        <div className="bg-slate-800 rounded-lg p-5 border border-slate-700">
          <div className="flex flex-wrap items-center gap-3 mb-1">
            <FileText className="h-5 w-5 text-blue-400" />
            <h3 className="font-medium text-white">{t('releaseNotes.title')}</h3>
            <span className="text-sm font-mono text-slate-400">v{releaseNotes.current_version}</span>
            {releaseNotes.source === 'changelog' && (
              <span className="text-xs text-amber-400/80">{t('releaseNotes.fromChangelog')}</span>
            )}
          </div>
          {releaseNotes.since_version && (
            <p className="text-sm text-slate-500 mb-4 ml-8">
              {t('releaseNotes.since', { version: releaseNotes.since_version })}
            </p>
          )}
          <div className="space-y-5 ml-8">
            {releaseNotes.releases.map((r) => (
              <div key={r.version}>
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  <span className="font-medium text-white">v{r.version}</span>
                  {r.is_prerelease && (
                    <span className="px-2 py-0.5 bg-amber-500/20 text-amber-400 text-xs rounded">
                      {t('preRelease.badge')}
                    </span>
                  )}
                  {r.date && (
                    <span className="text-xs text-slate-500">
                      {new Date(r.date).toLocaleDateString()}
                    </span>
                  )}
                  {r.url && (
                    <a
                      href={r.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-blue-400 hover:underline"
                    >
                      {t('releaseNotes.viewOnGitHub')}
                    </a>
                  )}
                </div>
                <div className={PROSE}>
                  <Markdown>{r.body_markdown}</Markdown>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Changelog (what an update brings) */}
      {checkResult?.update_available && checkResult.changelog.length > 0 && (
        <div className="bg-slate-800 rounded-lg p-5 border border-slate-700">
          <h3 className="font-medium text-white mb-4">{t('changelog.title')}</h3>
          <div className="space-y-4">
            {checkResult.changelog.map((entry, i) => (
              <div key={i} className="border-l-2 border-blue-500/50 pl-4">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium text-white">v{entry.version}</span>
                  {entry.is_prerelease && (
                    <span className="px-2 py-0.5 bg-amber-500/20 text-amber-400 text-xs rounded">
                      {t('changelog.prerelease')}
                    </span>
                  )}
                </div>
                {entry.body_markdown && (
                  <div className={PROSE}>
                    <Markdown>{entry.body_markdown}</Markdown>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Update Button */}
      {checkResult?.update_available && (
        <div className="flex justify-end gap-3">
          {!showUpdateConfirm ? (
            <button
              onClick={() => onSetShowUpdateConfirm(true)}
              disabled={!checkResult.can_update || updateLoading || !!currentUpdate}
              className="flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-lg transition-all touch-manipulation active:scale-95 font-medium"
            >
              <Download className="h-5 w-5" />
              {t('buttons.updateTo', { version: checkResult.latest_version?.version })}
            </button>
          ) : (
            <div className="flex items-center gap-3 p-3 bg-slate-700 rounded-lg">
              <span className="text-sm text-slate-300">{t('buttons.confirmUpdate')}</span>
              <button
                onClick={onStartUpdate}
                disabled={updateLoading}
                className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm transition-all touch-manipulation active:scale-95"
              >
                {updateLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : t('buttons.yesUpdate')}
              </button>
              <button
                onClick={() => onSetShowUpdateConfirm(false)}
                className="px-4 py-1.5 bg-slate-600 hover:bg-slate-500 text-white rounded text-sm transition-all touch-manipulation active:scale-95"
              >
                {t('common:cancel')}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
