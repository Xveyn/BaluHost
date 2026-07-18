import logoMark from '../../assets/baluhost-logo.png';
import { useFormattedVersion } from '../../contexts/VersionContext';
import { DeveloperBadge } from '../ui/DeveloperBadge';
import { isPi } from '../../lib/features';

interface BrandSizeConfig {
  box: string;
  pi: string;
  title: string;
  // Omitted for 'compact' — that variant never renders the version line.
  version?: string;
}

const SIZES: Record<'desktop' | 'mobile' | 'compact', BrandSizeConfig> = {
  desktop: { box: 'h-12 w-12 p-[3px]', pi: 'text-sm', title: 'text-lg', version: 'text-xs uppercase tracking-[0.35em] text-slate-100-tertiary' },
  mobile: { box: 'h-10 w-10 p-[3px]', pi: 'text-xs', title: 'text-base', version: 'text-[10px] uppercase tracking-[0.3em] text-slate-100-tertiary' },
  compact: { box: 'h-8 w-8 p-[2px]', pi: 'text-[10px]', title: 'text-sm' },
};

export function SidebarBrand({ variant }: { variant: keyof typeof SIZES }) {
  const formattedVersion = useFormattedVersion('');
  const s = SIZES[variant];
  const gap = variant === 'compact' ? 'gap-2' : 'gap-3';
  return (
    <div className={`flex items-center ${gap}`}>
      <div className={`relative flex ${s.box} items-center justify-center rounded-full bg-slate-950-tertiary`}>
        {isPi ? (
          <div className={`flex h-full w-full items-center justify-center rounded-full bg-gradient-to-br from-sky-500 to-indigo-600 ${s.pi} font-bold text-white`}>BP</div>
        ) : (
          <img src={logoMark} alt={variant === 'compact' ? 'BaluHost' : 'BaluHost logo'} className="h-full w-full rounded-full" />
        )}
      </div>
      {variant === 'compact' ? (
        <span className={`${s.title} font-semibold`}>{isPi ? 'BaluPi' : 'BaluHost'}</span>
      ) : (
        <div>
          <p className={`${s.title} font-semibold tracking-wide`}>{isPi ? 'BaluPi' : 'BaluHost'}</p>
          <p className={s.version}>{formattedVersion}{__BUILD_TYPE__ === 'dev' && <span className="font-mono"> · {__GIT_COMMIT__}</span>}</p>
          <DeveloperBadge />
        </div>
      )}
    </div>
  );
}
