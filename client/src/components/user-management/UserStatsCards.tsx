import { useTranslation } from 'react-i18next';
import { Users, CheckCircle, XCircle, Shield } from 'lucide-react';

interface UserStatsCardsProps {
  stats: { total: number; active: number; inactive: number; admins: number };
}

export function UserStatsCards({ stats }: UserStatsCardsProps) {
  const { t } = useTranslation('admin');

  const cards = [
    { label: t('users.stats.totalUsers'), value: stats.total, color: 'text-white', icon: Users, iconColor: 'text-sky-500' },
    { label: t('users.stats.active'), value: stats.active, color: 'text-green-400', icon: CheckCircle, iconColor: 'text-green-500' },
    { label: t('users.stats.inactive'), value: stats.inactive, color: 'text-slate-400', icon: XCircle, iconColor: 'text-slate-500' },
    { label: t('users.stats.admins'), value: stats.admins, color: 'text-sky-400', icon: Shield, iconColor: 'text-sky-500' },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
      {cards.map((card) => (
        <div key={card.label} className="card border-slate-800/60 bg-slate-900/55 p-3 sm:p-4">
          <div className="flex items-center justify-between">
            <div className="min-w-0 flex-1">
              <p className="text-xs sm:text-sm text-slate-400 truncate">{card.label}</p>
              <p className={`mt-1 text-xl sm:text-2xl font-semibold ${card.color}`}>{card.value}</p>
            </div>
            <card.icon className={`h-6 w-6 sm:h-8 sm:w-8 ${card.iconColor} flex-shrink-0 ml-2`} />
          </div>
        </div>
      ))}
    </div>
  );
}
