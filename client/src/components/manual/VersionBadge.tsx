import { useTranslation } from 'react-i18next';

interface VersionBadgeProps {
  /** The version the article was last verified for */
  articleVersion: string;
  /** The current app version */
  appVersion: string;
}

/** Compare semver-like version strings: returns true if a >= b */
function isVersionCurrent(articleVer: string, appVer: string): boolean {
  const parse = (v: string) => v.replace(/^v/, '').split('.').map(Number);
  const a = parse(articleVer);
  const b = parse(appVer);
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    if ((a[i] ?? 0) < (b[i] ?? 0)) return false;
    if ((a[i] ?? 0) > (b[i] ?? 0)) return true;
  }
  return true; // equal
}

export default function VersionBadge({ articleVersion, appVersion }: VersionBadgeProps) {
  const { t } = useTranslation('manual');
  const current = isVersionCurrent(articleVersion, appVersion);

  if (current) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
        v{articleVersion}
      </span>
    );
  }

  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono bg-amber-500/15 text-amber-400 border border-amber-500/30"
      title={t('staleness', { version: articleVersion })}
    >
      v{articleVersion}
    </span>
  );
}
