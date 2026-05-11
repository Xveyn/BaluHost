import { Globe, ShieldOff, BarChart3, Layers } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { StatCard } from '../ui/StatCard';
import type { PiholeSummary } from '../../api/pihole';

interface PiholeSummaryCardsProps {
  summary: PiholeSummary | null;
  loading: boolean;
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return n.toLocaleString();
}

function SkeletonCard() {
  return (
    <div className="card border-slate-700/40 bg-gradient-to-br from-slate-700/10 to-transparent p-3 sm:p-5">
      <div className="h-3 w-24 animate-pulse rounded bg-slate-700" />
      <div className="mt-2 h-8 w-28 animate-pulse rounded bg-slate-700" />
    </div>
  );
}

export default function PiholeSummaryCards({ summary, loading }: PiholeSummaryCardsProps) {
  const { t } = useTranslation('pihole');

  if (loading || !summary) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  const pctBlocked =
    summary.total_queries > 0
      ? ((summary.blocked_queries / summary.total_queries) * 100).toFixed(1)
      : '0.0';

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard
        label={t('summary.totalQueries')}
        value={formatNumber(summary.total_queries)}
        color="blue"
        icon={<Globe className="h-5 w-5 sm:h-6 sm:w-6 text-blue-400" />}
      />
      <StatCard
        label={t('summary.blockedQueries')}
        value={formatNumber(summary.blocked_queries)}
        color="red"
        icon={<ShieldOff className="h-5 w-5 sm:h-6 sm:w-6 text-red-400" />}
      />
      <StatCard
        label={t('summary.percentBlocked')}
        value={`${pctBlocked}%`}
        color="amber"
        icon={<BarChart3 className="h-5 w-5 sm:h-6 sm:w-6 text-amber-400" />}
      />
      <StatCard
        label={t('summary.uniqueDomains')}
        value={formatNumber(summary.unique_domains)}
        color="sky"
        icon={<Layers className="h-5 w-5 sm:h-6 sm:w-6 text-sky-400" />}
      />
    </div>
  );
}
