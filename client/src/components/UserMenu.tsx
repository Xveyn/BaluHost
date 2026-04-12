import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { UserPlus, ChevronRight, Shield, User as UserIcon } from 'lucide-react';
import toast from 'react-hot-toast';
import { useAuth } from '../contexts/AuthContext';
import { useSystemMode } from '../hooks/useSystemMode';
import { apiClient } from '../lib/api';

interface UserPublic {
  id: number;
  username: string;
  role: string;
}

interface UsersResponse {
  users: UserPublic[];
}

export default function UserMenu() {
  const { t } = useTranslation('common');
  const { user, isAdmin, isImpersonating, impersonate } = useAuth();
  const { data: systemMode } = useSystemMode();
  const [open, setOpen] = useState(false);
  const [submenuOpen, setSubmenuOpen] = useState(false);
  const [users, setUsers] = useState<UserPublic[] | null>(null);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const canSwitchUser = systemMode?.dev_mode === true && isAdmin && !isImpersonating;

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
        setSubmenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const loadUsers = async () => {
    if (users !== null || loadingUsers) return;
    setLoadingUsers(true);
    try {
      const { data } = await apiClient.get<UsersResponse>('/api/users/');
      setUsers(data.users ?? []);
    } catch {
      toast.error('Failed to load users');
      setUsers([]);
    } finally {
      setLoadingUsers(false);
    }
  };

  const onSwitchToUser = async (targetId: number) => {
    try {
      await impersonate(targetId);
      setOpen(false);
      setSubmenuOpen(false);
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'Impersonation failed';
      toast.error(message);
    }
  };

  if (!user) return null;

  return (
    <div ref={rootRef} className="relative hidden md:block">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/40 px-3 py-1.5 transition hover:border-sky-500/50 hover:shadow-[0_0_12px_rgba(56,189,248,0.15)]"
      >
        <div className="flex flex-col text-left">
          <span className="text-sm font-medium text-slate-100">{user.username}</span>
          <span className="text-[11px] text-slate-400">{isAdmin ? 'Admin' : 'User'}</span>
        </div>
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-64 rounded-xl border border-slate-800 bg-slate-900/95 p-2 shadow-2xl backdrop-blur-xl">
          {canSwitchUser ? (
            <div
              className="relative"
              onMouseEnter={() => {
                setSubmenuOpen(true);
                void loadUsers();
              }}
              onMouseLeave={() => setSubmenuOpen(false)}
            >
              <button
                type="button"
                className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm text-slate-200 transition hover:bg-slate-800/70"
              >
                <span className="flex items-center gap-2">
                  <UserPlus className="h-4 w-4" />
                  {t('impersonation.switchToUser')}
                </span>
                <ChevronRight className="h-4 w-4 text-slate-400" />
              </button>

              {submenuOpen && (
                <div className="absolute right-full top-0 mr-1 w-64 max-h-80 overflow-y-auto rounded-xl border border-slate-800 bg-slate-900/95 p-2 shadow-2xl backdrop-blur-xl">
                  {loadingUsers && (
                    <div className="px-3 py-2 text-sm text-slate-400">
                      {t('impersonation.loading')}
                    </div>
                  )}
                  {!loadingUsers && users !== null && users.length === 0 && (
                    <div className="px-3 py-2 text-sm text-slate-400">
                      {t('impersonation.empty')}
                    </div>
                  )}
                  {!loadingUsers &&
                    users !== null &&
                    users
                      .filter((u) => u.id !== user.id)
                      .map((u) => (
                        <button
                          key={u.id}
                          type="button"
                          onClick={() => void onSwitchToUser(u.id)}
                          className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm text-slate-200 transition hover:bg-slate-800/70"
                        >
                          <span className="flex items-center gap-2">
                            {u.role === 'admin' ? (
                              <Shield className="h-4 w-4 text-amber-400" />
                            ) : (
                              <UserIcon className="h-4 w-4 text-slate-400" />
                            )}
                            {u.username}
                          </span>
                          <span
                            className={
                              u.role === 'admin'
                                ? 'rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-300'
                                : 'rounded-full bg-slate-700/50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-300'
                            }
                          >
                            {u.role}
                          </span>
                        </button>
                      ))}
                </div>
              )}
            </div>
          ) : (
            <div className="px-3 py-2 text-xs text-slate-500">{user.username}</div>
          )}
        </div>
      )}
    </div>
  );
}
