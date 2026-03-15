import {
  Download,
  CheckCircle,
  AlertTriangle,
  GitBranch,
  Clock,
  Loader2,
  Zap,
  Sparkles,
  Bug,
  Wrench,
  Cog,
  BookOpen,
  TestTube,
  Paintbrush,
  CircleDot,
  FileText,
  Package,
} from 'lucide-react';
import type { UpdateCheckResponse, ReleaseNotesResponse } from '../../api/updates';
import { isUpdateInProgress, type UpdateProgressResponse } from '../../api/updates';
import UpdateProgress from './UpdateProgress';

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  sparkles: <Sparkles className="h-4 w-4" />,
  bug: <Bug className="h-4 w-4" />,
  zap: <Zap className="h-4 w-4" />,
  wrench: <Wrench className="h-4 w-4" />,
  cog: <Cog className="h-4 w-4" />,
  'book-open': <BookOpen className="h-4 w-4" />,
  'test-tube': <TestTube className="h-4 w-4" />,
  paintbrush: <Paintbrush className="h-4 w-4" />,
  'circle-dot': <CircleDot className="h-4 w-4" />,
};

const CATEGORY_COLORS: Record<string, string> = {
  Features: 'text-emerald-400',
  'Bug Fixes': 'text-rose-400',
  Performance: 'text-amber-400',
  Refactoring: 'text-sky-400',
  Maintenance: 'text-slate-400',
  Documentation: 'text-violet-400',
  Tests: 'text-cyan-400',
  Other: 'text-slate-400',
};

interface UpdateOverviewTabProps {
  t: (key: string, options?: Record<string, unknown>) => string;
  checkResult: UpdateCheckResponse | null;
  currentUpdate: UpdateProgressResponse | null;
  releaseNotes: ReleaseNotesResponse | null;
  updateLoading: boolean;
  rollbackLoading: boolean;
  cancelLoading: boolean;
  devUpdateLoading: boolean;
  showUpdateConfirm: boolean;
  showDevUpdateConfirm: boolean;
  onSetShowUpdateConfirm: (show: boolean) => void;
  onSetShowDevUpdateConfirm: (show: boolean) => void;
  onSetShowRollbackConfirm: (show: boolean) => void;
  onStartUpdate: () => void;
  onStartDevUpdate: () => void;
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
  devUpdateLoading,
  showUpdateConfirm,
  showDevUpdateConfirm,
  onSetShowUpdateConfirm,
  onSetShowDevUpdateConfirm,
  onSetShowRollbackConfirm,
  onStartUpdate,
  onStartDevUpdate,
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
              <div className="text-3xl font-bold text-white">
                v{checkResult.current_version.version}
              </div>
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <GitBranch className="h-4 w-4" />
                <span className="font-mono">
                  {checkResult.current_version.commit_short}
                </span>
                {checkResult.current_version.tag && (
                  <span className="px-2 py-0.5 bg-slate-700 rounded text-xs">
                    {checkResult.current_version.tag}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 text-sm">
                {checkResult.current_version.is_dev_build ? (
                  <span className="px-2 py-0.5 bg-amber-500/20 text-amber-400 rounded text-xs font-medium">
                    {t('version.devBuild')}
                  </span>
                ) : (
                  <span className="text-emerald-400">Stable</span>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Available Update */}
        <div
          className={`bg-slate-800 rounded-lg p-5 border ${
            checkResult?.update_available
              ? 'border-blue-500/50 bg-blue-500/5'
              : !checkResult?.update_available && checkResult?.dev_version_available
                ? 'border-amber-500/30 bg-amber-500/5'
                : 'border-slate-700'
          }`}
        >
          <div className="flex items-center gap-2 mb-4">
            {checkResult?.update_available ? (
              <Zap className="h-5 w-5 text-blue-400" />
            ) : !checkResult?.update_available && checkResult?.dev_version_available ? (
              <GitBranch className="h-5 w-5 text-amber-400" />
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
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <GitBranch className="h-4 w-4" />
                <span className="font-mono">
                  {checkResult.latest_version.commit_short}
                </span>
              </div>
              {checkResult.last_checked && (
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <Clock className="h-3 w-3" />
                  {t('version.lastChecked')} {new Date(checkResult.last_checked).toLocaleString()}
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-slate-400">
                {t('version.upToDateDesc')}
              </p>
              {checkResult?.dev_version_available && checkResult.dev_version && (
                <div className="pt-2 border-t border-slate-700/50 space-y-2">
                  <div className="flex items-center gap-2 text-sm text-amber-400">
                    <GitBranch className="h-3.5 w-3.5" />
                    <span className="font-medium">{t('version.devVersionAvailable')}</span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-slate-400">
                    <span className="font-mono">{checkResult.dev_version.commit_short}</span>
                    <span>{t('version.devCommitsAhead', { count: checkResult.dev_commits_ahead ?? 0 })}</span>
                  </div>
                  {checkResult.dev_commits && checkResult.dev_commits.length > 0 && (
                    <div className="space-y-1 max-h-48 overflow-y-auto">
                      {checkResult.dev_commits.map((commit) => (
                        <div key={commit.hash_short} className="flex items-start gap-2 text-xs">
                          <span className="font-mono text-slate-500 shrink-0">{commit.hash_short}</span>
                          <span className="text-slate-300 break-all">
                            {commit.type && (
                              <span className={`font-medium ${
                                commit.type === 'feat' ? 'text-emerald-400' :
                                commit.type === 'fix' ? 'text-blue-400' :
                                'text-slate-400'
                              }`}>
                                {commit.type}{commit.scope ? `(${commit.scope})` : ''}:
                              </span>
                            )}{' '}
                            {commit.message.includes(':') ? commit.message.split(':').slice(1).join(':').trim() : commit.message}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                  {/* Dev Install Button */}
                  <div className="pt-2">
                    {!showDevUpdateConfirm ? (
                      <button
                        onClick={() => onSetShowDevUpdateConfirm(true)}
                        disabled={devUpdateLoading || !!currentUpdate}
                        className="flex items-center gap-2 px-3 py-1.5 bg-amber-600 hover:bg-amber-700 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-lg transition-all touch-manipulation active:scale-95 text-xs font-medium"
                      >
                        <Download className="h-3.5 w-3.5" />
                        {t('buttons.installDevVersion')}
                      </button>
                    ) : (
                      <div className="space-y-2">
                        <p className="text-xs text-amber-400/80">
                          <AlertTriangle className="h-3 w-3 inline mr-1" />
                          {t('version.devWarning')}
                        </p>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={onStartDevUpdate}
                            disabled={devUpdateLoading}
                            className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded text-xs transition-all touch-manipulation active:scale-95"
                          >
                            {devUpdateLoading ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Download className="h-3.5 w-3.5" />
                            )}
                            {t('buttons.confirmDevInstall')}
                          </button>
                          <button
                            onClick={() => onSetShowDevUpdateConfirm(false)}
                            className="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white rounded text-xs transition-all touch-manipulation active:scale-95"
                          >
                            {t('common:cancel')}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
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

      {/* Release Notes */}
      {releaseNotes && releaseNotes.categories.length > 0 && (
        <div className="bg-slate-800 rounded-lg p-5 border border-slate-700">
          <div className="flex items-center gap-3 mb-1">
            <FileText className="h-5 w-5 text-blue-400" />
            <h3 className="font-medium text-white">{t('releaseNotes.title')}</h3>
            <span className="text-sm font-mono text-slate-400">v{releaseNotes.version}</span>
          </div>
          {releaseNotes.previous_version && (
            <p className="text-sm text-slate-500 mb-4 ml-8">
              {t('releaseNotes.since', { version: releaseNotes.previous_version })}
            </p>
          )}
          <div className="space-y-4 ml-8">
            {releaseNotes.categories.map((category) => (
              <div key={category.name}>
                <div className="flex items-center gap-2 mb-2">
                  <span className={CATEGORY_COLORS[category.name] || 'text-slate-400'}>
                    {CATEGORY_ICONS[category.icon] || <CircleDot className="h-4 w-4" />}
                  </span>
                  <h4 className={`text-sm font-medium ${CATEGORY_COLORS[category.name] || 'text-slate-400'}`}>
                    {category.name}
                  </h4>
                </div>
                <ul className="space-y-1 text-sm text-slate-300 ml-6">
                  {category.changes.map((change, j) => (
                    <li key={j}>• {change}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Changelog */}
      {checkResult?.update_available && checkResult.changelog.length > 0 && (
        <div className="bg-slate-800 rounded-lg p-5 border border-slate-700">
          <h3 className="font-medium text-white mb-4">{t('changelog.title')}</h3>
          <div className="space-y-4">
            {checkResult.changelog.map((entry, i) => (
              <div key={i} className="border-l-2 border-blue-500/50 pl-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="font-medium text-white">v{entry.version}</span>
                  {entry.is_prerelease && (
                    <span className="px-2 py-0.5 bg-amber-500/20 text-amber-400 text-xs rounded">
                      {t('changelog.prerelease')}
                    </span>
                  )}
                </div>
                {entry.changes.length > 0 && (
                  <ul className="space-y-1 text-sm text-slate-300">
                    {entry.changes.map((change, j) => (
                      <li key={j}>• {change}</li>
                    ))}
                  </ul>
                )}
                {entry.breaking_changes.length > 0 && (
                  <div className="mt-2">
                    <span className="text-rose-400 text-sm font-medium">
                      {t('changelog.breakingChanges')}
                    </span>
                    <ul className="space-y-1 text-sm text-rose-300">
                      {entry.breaking_changes.map((change, j) => (
                        <li key={j}>• {change}</li>
                      ))}
                    </ul>
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
                {updateLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  t('buttons.yesUpdate')
                )}
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
