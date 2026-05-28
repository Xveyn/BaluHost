import React from 'react';
import { Link } from 'react-router-dom';

export type PillTone = 'success' | 'info' | 'warning' | 'danger' | 'neutral';

export interface PillProps {
  tone: PillTone;
  label: string;
  value?: string | null;
  href: string;
  icon?: React.ReactNode;
  ariaLabel?: string;
}

const TONE_CLASSES: Record<PillTone, string> = {
  success: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20',
  info: 'border-sky-500/40 bg-sky-500/10 text-sky-300 hover:bg-sky-500/20',
  warning: 'border-amber-500/40 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20',
  danger: 'border-rose-500/40 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20',
  neutral: 'border-slate-700 bg-slate-800/60 text-slate-300 hover:bg-slate-800',
};

export function Pill({ tone, label, value, href, icon, ariaLabel }: PillProps) {
  const aria = ariaLabel ?? (value ? `${label}: ${value}` : label);
  return (
    <Link
      to={href}
      aria-label={aria}
      title={aria}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60 ${TONE_CLASSES[tone]}`}
    >
      {icon}
      <span>{label}</span>
      {value != null && value !== '' && <span className="opacity-80">{value}</span>}
    </Link>
  );
}
