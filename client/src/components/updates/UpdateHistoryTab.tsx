import {
  GitBranch,
  GitCommit,
  Loader2,
  Tag,
} from 'lucide-react';
import type { ReleaseInfo, VersionHistoryResponse } from '../../api/updates';

interface UpdateHistoryTabProps {
  t: (key: string, options?: Record<string, unknown>) => string;
  releases: ReleaseInfo[];
  releasesLoading: boolean;
  versionHistory: VersionHistoryResponse | null;
  versionHistoryLoading: boolean;
}

export default function UpdateHistoryTab({
  t,
  releases,
  releasesLoading,
  versionHistory,
  versionHistoryLoading,
}: UpdateHistoryTabProps) {
  return (
    <>
      {/* All Releases Section */}
      <div className="mt-6 bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-700 bg-slate-800/80">
          <h3 className="font-medium text-white flex items-center gap-2">
            <Tag className="h-4 w-4 text-slate-400" />
            {t('releases.title')}
          </h3>
          <p className="text-xs text-slate-400 mt-1">{t('releases.description')}</p>
        </div>
        {releasesLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
          </div>
        ) : releases.length === 0 ? (
          <div className="px-4 py-8 text-center text-slate-400">
            {t('releases.noReleases')}
          </div>
        ) : (
          <div className="divide-y divide-slate-700/50">
            {releases.map((release) => (
              <div
                key={release.tag}
                className="px-4 py-3 flex items-center justify-between hover:bg-slate-700/30 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <span className="font-mono text-white">{release.tag}</span>
                  <span className="font-mono text-xs text-slate-500">{release.commit_short}</span>
                </div>
                <div className="flex items-center gap-3">
                  {release.date && (
                    <span className="text-sm text-slate-400">
                      {new Date(release.date).toLocaleDateString()}
                    </span>
                  )}
                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                      release.is_prerelease
                        ? 'bg-amber-500/20 text-amber-400'
                        : 'bg-emerald-500/20 text-emerald-400'
                    }`}
                  >
                    {release.is_prerelease ? t('releases.prerelease') : t('releases.stable')}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Version History Section */}
      <div className="mt-6 bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-700 bg-slate-800/80">
          <h3 className="font-medium text-white flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-slate-400" />
            {t('versionHistory.title')}
          </h3>
          <p className="text-xs text-slate-400 mt-1">{t('versionHistory.description')}</p>
        </div>
        {versionHistoryLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
          </div>
        ) : !versionHistory || versionHistory.versions.length === 0 ? (
          <div className="px-4 py-8 text-center text-slate-400">
            {t('versionHistory.noHistory')}
          </div>
        ) : (
          <div className="divide-y divide-slate-700/50">
            {versionHistory.versions.map((entry) => {
              const isCurrent =
                entry.version === versionHistory.current_version &&
                entry.git_commit_short === versionHistory.current_commit;
              return (
                <div
                  key={entry.id}
                  className="px-4 py-3 hover:bg-slate-700/30 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-white font-medium">
                        v{entry.version}
                      </span>
                      <span className="font-mono text-xs text-slate-500">
                        {entry.git_commit_short}
                      </span>
                      {entry.git_branch && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-slate-700 text-slate-300">
                          <GitBranch className="h-3 w-3" />
                          {entry.git_branch}
                        </span>
                      )}
                      {isCurrent && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-emerald-500/20 text-emerald-400">
                          {t('versionHistory.current')}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-sm text-slate-400">
                      <span title={t('versionHistory.timesStarted', { count: entry.times_started })}>
                        {t('versionHistory.timesStarted', { count: entry.times_started })}
                      </span>
                    </div>
                  </div>
                  <div className="mt-1.5 flex items-center gap-4 text-xs text-slate-500">
                    <span>
                      {t('versionHistory.firstSeen')}: {new Date(entry.first_seen).toLocaleDateString()}
                    </span>
                    <span>
                      {t('versionHistory.lastSeen')}: {new Date(entry.last_seen).toLocaleDateString()}
                    </span>
                    {entry.python_version && (
                      <span>
                        {t('versionHistory.python')} {entry.python_version}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
