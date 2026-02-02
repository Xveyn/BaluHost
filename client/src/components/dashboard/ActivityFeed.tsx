/**
 * Activity Feed component for Dashboard
 * Shows recent audit log entries
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useActivityFeed } from '../../hooks/useActivityFeed';
import {
  Upload,
  Download,
  Trash2,
  Plus,
  User,
  Move,
  Copy,
  Share2,
  FileText,
  AlertCircle,
} from 'lucide-react';

interface ActivityFeedProps {
  limit?: number;
}

// Get icon component for activity type
function ActivityIcon({ type, success }: { type: string; success: boolean }) {
  const iconClass = success ? 'text-sky-400' : 'text-rose-400';

  const iconMap: Record<string, React.ReactNode> = {
    upload: <Upload className={`h-4 w-4 ${iconClass}`} />,
    download: <Download className={`h-4 w-4 ${iconClass}`} />,
    delete: <Trash2 className={`h-4 w-4 ${iconClass}`} />,
    create: <Plus className={`h-4 w-4 ${iconClass}`} />,
    user: <User className={`h-4 w-4 ${iconClass}`} />,
    move: <Move className={`h-4 w-4 ${iconClass}`} />,
    copy: <Copy className={`h-4 w-4 ${iconClass}`} />,
    share: <Share2 className={`h-4 w-4 ${iconClass}`} />,
    file: <FileText className={`h-4 w-4 ${iconClass}`} />,
  };

  return iconMap[type] || <FileText className={`h-4 w-4 ${iconClass}`} />;
}

export const ActivityFeed: React.FC<ActivityFeedProps> = ({ limit = 5 }) => {
  const { t } = useTranslation(['dashboard', 'common']);
  const navigate = useNavigate();
  const { activities, loading, error } = useActivityFeed({ limit, days: 1 });

  const handleViewLogs = () => {
    navigate('/logging');
  };

  return (
    <div className="card border-slate-800/50 bg-slate-900/55">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{t('dashboard:activity.title')}</p>
          <h2 className="mt-2 text-xl font-semibold text-white">{t('dashboard:activity.liveOperations')}</h2>
        </div>
        <button
          onClick={handleViewLogs}
          className="rounded-full border border-slate-700/70 px-3 py-1 text-xs text-slate-400 transition hover:border-slate-500 hover:text-white"
        >
          {t('dashboard:activity.viewSystemLogs')}
        </button>
      </div>

      <div className="mt-6 space-y-4">
        {loading ? (
          // Loading state
          <div className="flex flex-col gap-3">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="flex items-center justify-between rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-3"
              >
                <div className="flex items-center gap-4">
                  <div className="h-9 w-9 rounded-xl bg-slate-800 animate-pulse" />
                  <div className="space-y-2">
                    <div className="h-4 w-32 rounded bg-slate-800 animate-pulse" />
                    <div className="h-3 w-48 rounded bg-slate-800/50 animate-pulse" />
                  </div>
                </div>
                <div className="h-3 w-16 rounded bg-slate-800/50 animate-pulse" />
              </div>
            ))}
          </div>
        ) : error ? (
          // Error state
          <div className="flex items-center gap-3 rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-4 text-rose-200">
            <AlertCircle className="h-5 w-5 shrink-0" />
            <span className="text-sm">{t('dashboard:activity.failedToLoad', { error })}</span>
          </div>
        ) : activities.length === 0 ? (
          // Empty state
          <div className="flex flex-col items-center justify-center rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-8 text-center">
            <FileText className="h-8 w-8 text-slate-600 mb-2" />
            <p className="text-sm text-slate-400">{t('dashboard:activity.noRecentActivity')}</p>
            <p className="text-xs text-slate-500 mt-1">{t('dashboard:activity.operationsAppearHere')}</p>
          </div>
        ) : (
          // Activity list
          activities.map((item) => (
            <div
              key={item.id}
              className="flex items-center justify-between rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-3 transition hover:border-sky-500/30"
            >
              <div className="flex items-center gap-4">
                <div className={`flex h-9 w-9 items-center justify-center rounded-xl ${
                  item.success ? 'bg-slate-950/70' : 'bg-rose-950/50'
                }`}>
                  <ActivityIcon type={item.icon} success={item.success} />
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-100">{item.title}</p>
                  <p className="text-xs text-slate-500 truncate max-w-[250px] sm:max-w-[350px]">
                    {item.detail}
                  </p>
                </div>
              </div>
              <span className="text-xs text-slate-500 shrink-0 ml-2">{item.ago}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default ActivityFeed;
