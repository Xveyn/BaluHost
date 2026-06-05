/**
 * GameLibrariesCard -- shows detected game libraries (Steam et al.) with a
 * per-library aggregate and an expandable per-game list, for the Storage tab.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Gamepad2, ChevronDown, ChevronRight } from 'lucide-react';
import { formatBytes } from '../../lib/formatters';
import type { GameLibrary } from '../../api/games';

interface GameLibrariesCardProps {
  libraries: GameLibrary[] | null;  // null = still loading
  available: boolean;
}

export default function GameLibrariesCard({ libraries, available }: GameLibrariesCardProps) {
  const { t } = useTranslation('settings');
  const [openLibs, setOpenLibs] = useState<Record<string, boolean>>({});

  const toggle = (key: string) =>
    setOpenLibs((prev) => ({ ...prev, [key]: !prev[key] }));

  return (
    <div className="card border-slate-800/60 bg-slate-900/55 shadow-[0_4px_24px_rgba(99,102,241,0.06)] hover:shadow-[0_8px_32px_rgba(99,102,241,0.12)] transition-shadow">
      <h3 className="text-base sm:text-lg font-semibold mb-4 flex items-center">
        <Gamepad2 className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-indigo-400" />
        {t('storage.games.title')}
      </h3>

      {libraries === null ? (
        <div className="space-y-3 animate-pulse">
          <div className="h-16 rounded-lg bg-slate-700/30" />
        </div>
      ) : !available || libraries.length === 0 ? (
        <div className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/60 border border-slate-700/40">
          <Gamepad2 className="w-5 h-5 text-slate-500" />
          <p className="text-sm text-slate-400">{t('storage.games.empty')}</p>
        </div>
      ) : (
        <div className="space-y-4">
          {libraries.map((lib, idx) => {
            const key = `${lib.provider}:${lib.path}:${idx}`;
            const open = !!openLibs[key];
            const gamesMax = Math.max(...lib.games.map((g) => g.size_bytes), 1);
            return (
              <div key={key} className="p-4 rounded-xl bg-slate-800/40 border border-slate-700/30">
                <button
                  type="button"
                  onClick={() => toggle(key)}
                  className="w-full flex items-center justify-between gap-3 text-left"
                  aria-expanded={open}
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                        {lib.provider_name}
                      </span>
                      <span className="text-sm font-semibold tabular-nums">{formatBytes(lib.total_bytes)}</span>
                    </div>
                    <p className="text-xs text-slate-500 truncate mt-1">{lib.path}</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-xs text-slate-400">
                      {t('storage.games.count', { count: lib.game_count })}
                    </span>
                    {open
                      ? <ChevronDown className="h-4 w-4 text-slate-500" />
                      : <ChevronRight className="h-4 w-4 text-slate-500" />}
                  </div>
                </button>

                {open && (
                  <ul className="mt-3 space-y-2 border-t border-slate-700/40 pt-3">
                    {lib.games.map((g) => (
                      <li
                        key={g.app_id}
                        className="rounded px-2 -mx-2 py-1.5 hover:bg-slate-800/30 transition-colors"
                      >
                        <div className="flex justify-between gap-2 text-xs sm:text-sm">
                          <span className="text-slate-300 truncate">{g.name}</span>
                          <span className="text-slate-400 tabular-nums shrink-0">{formatBytes(g.size_bytes)}</span>
                        </div>
                        <div className="mt-1 h-1 rounded-full bg-slate-700/30 overflow-hidden">
                          <div
                            className="h-full rounded-full bg-indigo-500/50"
                            style={{ width: `${Math.max((g.size_bytes / gamesMax) * 100, 1)}%` }}
                          />
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
