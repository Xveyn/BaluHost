import { useTranslation } from 'react-i18next';
import {
  Server,
  Smartphone,
  Monitor,
  ChevronRight,
  BookOpen,
} from 'lucide-react';
import * as Icons from 'lucide-react';
import type { DocsGroupInfo } from '../../hooks/useDocsIndex';

interface DocsOverviewProps {
  groups: DocsGroupInfo[];
  version: string | null;
  onSelectGroup: (groupId: string) => void;
}

function getIcon(name: string, className = 'h-5 w-5'): React.ReactNode {
  const pascal = name
    .split('-')
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join('');
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const IconComp = (Icons as Record<string, any>)[pascal];
  if (IconComp) return <IconComp className={className} />;
  return <Icons.FileText className={className} />;
}

const infraCards = [
  {
    key: 'server',
    icon: Server,
    gradient: 'from-sky-500 to-blue-600',
    border: 'border-sky-500/30',
    glow: 'group-hover:shadow-sky-500/20',
  },
  {
    key: 'app',
    icon: Smartphone,
    gradient: 'from-emerald-500 to-teal-600',
    border: 'border-emerald-500/30',
    glow: 'group-hover:shadow-emerald-500/20',
  },
  {
    key: 'desktop',
    icon: Monitor,
    gradient: 'from-violet-500 to-purple-600',
    border: 'border-violet-500/30',
    glow: 'group-hover:shadow-violet-500/20',
  },
] as const;

export default function DocsOverview({ groups, version, onSelectGroup }: DocsOverviewProps) {
  const { t } = useTranslation('manual');

  return (
    <div className="space-y-10">
      {/* Hero */}
      <div className="relative overflow-hidden rounded-2xl border border-slate-800/60 bg-gradient-to-br from-slate-900/80 via-slate-900/60 to-slate-800/40 p-6 sm:p-8 shadow-[0_20px_60px_rgba(2,6,23,0.55)] backdrop-blur-xl">
        <div className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-[radial-gradient(circle_at_center,_rgba(56,189,248,0.12),_transparent_60%)] blur-2xl" />
        <div className="pointer-events-none absolute -left-16 bottom-0 h-48 w-48 rounded-full bg-[radial-gradient(circle_at_center,_rgba(124,58,237,0.10),_transparent_60%)] blur-2xl" />

        <div className="relative flex items-center gap-4 sm:gap-5">
          <div className="flex h-14 w-14 sm:h-16 sm:w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-sky-500 via-indigo-500 to-violet-600 text-xl sm:text-2xl font-bold text-white shadow-lg shadow-indigo-500/25 flex-shrink-0">
            BH
          </div>
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-white">BaluHost</h1>
            <p className="text-slate-400 text-sm sm:text-base mt-1">
              {t('overview.subtitle')}
            </p>
            {version && (
              <span className="inline-flex items-center gap-1.5 mt-2 px-2.5 py-0.5 rounded-lg text-xs font-mono bg-sky-500/10 text-sky-400 border border-sky-500/30">
                v{version}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Infrastructure */}
      <section>
        <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-800 text-slate-400">
            <Server className="h-4 w-4" />
          </span>
          {t('overview.infrastructure')}
        </h2>
        <div className="grid gap-4 sm:grid-cols-3">
          {infraCards.map(({ key, icon: Icon, gradient, border, glow }) => (
            <div
              key={key}
              className={`group relative overflow-hidden rounded-2xl border ${border} bg-slate-900/55 p-5 shadow-[0_8px_24px_rgba(2,6,23,0.4)] backdrop-blur-xl transition-all duration-300 hover:shadow-[0_14px_44px_rgba(56,189,248,0.15)] hover:border-slate-700/60 ${glow}`}
            >
              <div className={`flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br ${gradient} text-white shadow-lg mb-3`}>
                <Icon className="h-5 w-5" />
              </div>
              <h3 className="text-base font-semibold text-white mb-1">
                {t(`overview.${key}.title`)}
              </h3>
              <p className="text-sm text-slate-400 leading-relaxed">
                {t(`overview.${key}.description`)}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Documentation Groups */}
      <section>
        <div className="mb-4">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-800 text-slate-400">
              <BookOpen className="h-4 w-4" />
            </span>
            {t('overview.docs')}
          </h2>
          <p className="text-sm text-slate-500 mt-1 ml-9">
            {t('overview.docsSubtitle')}
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {groups.map((group) => (
            <button
              key={group.id}
              onClick={() => onSelectGroup(group.id)}
              className="group w-full text-left relative overflow-hidden rounded-2xl border border-slate-800/60 bg-slate-900/55 p-4 sm:p-5 shadow-[0_8px_24px_rgba(2,6,23,0.4)] backdrop-blur-xl hover:border-slate-700/60 hover:shadow-[0_14px_44px_rgba(56,189,248,0.15)] transition-all duration-200 touch-manipulation active:scale-[0.99]"
            >
              <div className="flex items-start gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 bg-slate-950/60 text-sky-400 group-hover:border-sky-500/40 transition-colors flex-shrink-0">
                  {getIcon(group.icon)}
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="text-sm sm:text-base font-medium text-white">
                    {group.label}
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {t(`overview.groupDescriptions.${group.id}`, '')}
                  </p>
                  <span className="inline-block mt-2 text-[11px] text-slate-600 tabular-nums">
                    {t('overview.articles', { count: group.articles.length })}
                  </span>
                </div>
                <ChevronRight className="h-5 w-5 text-slate-600 group-hover:text-slate-400 transition-colors flex-shrink-0 mt-1" />
              </div>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
