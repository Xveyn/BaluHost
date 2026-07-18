import { Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { AdminBadge } from '../ui/AdminBadge';
import { PluginBadge } from '../ui/PluginBadge';
import type { LayoutNavItem } from './layoutNavConfig';

interface SidebarNavProps {
  items: LayoutNavItem[];
  adminStartIndex: number;
  variant: 'desktop' | 'mobile';
  onNavigate?: () => void;
}

export function SidebarNav({ items, adminStartIndex, variant, onNavigate }: SidebarNavProps) {
  const location = useLocation();
  const { t } = useTranslation('common');
  const inactiveClass = variant === 'mobile'
    ? 'border-transparent text-slate-300 hover:border-slate-800'
    : 'border-transparent text-slate-300';

  return (
    <div className="space-y-1">
      {items.map((item, index) => {
        const active = location.pathname === item.path;
        const isFirstAdminItem = adminStartIndex >= 0 && index === adminStartIndex;
        return (
          <div key={item.path}>
            {isFirstAdminItem && (
              <div className="my-3 border-t border-slate-800/50 pt-3">
                <div className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">
                  {t('navigation.admin')}
                </div>
              </div>
            )}
            <Link
              to={item.path}
              onClick={onNavigate}
              className={`group flex items-center gap-3 rounded-xl border px-4 py-2.5 text-sm font-medium transition-all duration-200 ${
                active ? 'border-sky-500 bg-slate-900-hover text-sky-400' : inactiveClass
              }`}
            >
              <span
                className={`flex h-9 w-9 items-center justify-center rounded-xl border text-base transition-colors duration-200 ${
                  active
                    ? 'border-sky-500/40 bg-slate-950-secondary text-sky-400'
                    : 'border-slate-800 bg-slate-950 text-slate-100-tertiary group-hover:border-sky-500/30 group-hover:text-sky-400'
                }`}
              >
                {item.icon}
              </span>
              <div className="flex flex-col">
                <span className="flex items-center gap-2">
                  {item.label}
                  {item.adminOnly && <AdminBadge />}
                  {item.isPlugin && <PluginBadge />}
                </span>
                <span className="text-xs text-slate-100-tertiary">{item.description}</span>
              </div>
            </Link>
          </div>
        );
      })}
    </div>
  );
}
