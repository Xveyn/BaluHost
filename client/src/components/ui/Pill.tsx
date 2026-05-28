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
  /** Flat = no own chip border/bg (just tone-colored text); used inside the status-strip container. */
  flat?: boolean;
}

const TONE_CLASSES: Record<PillTone, string> = {
  success: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20',
  info: 'border-sky-500/40 bg-sky-500/10 text-sky-300 hover:bg-sky-500/20',
  warning: 'border-amber-500/40 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20',
  danger: 'border-rose-500/40 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20',
  neutral: 'border-slate-700 bg-slate-800/60 text-slate-300 hover:bg-slate-800',
};

const TONE_TEXT: Record<PillTone, string> = {
  success: 'text-emerald-300 hover:text-emerald-200',
  info: 'text-sky-300 hover:text-sky-200',
  warning: 'text-amber-300 hover:text-amber-200',
  danger: 'text-rose-300 hover:text-rose-200',
  neutral: 'text-slate-300 hover:text-slate-100',
};

export function Pill({ tone, label, value, href, icon, ariaLabel, flat = false }: PillProps) {
  const aria = ariaLabel ?? (value ? `${label}: ${value}` : label);
  const base = 'inline-flex items-center gap-1.5 text-xs font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60';
  const className = flat
    ? `${base} rounded px-1.5 py-0.5 ${TONE_TEXT[tone]}`
    : `${base} rounded-full border px-2.5 py-1 ${TONE_CLASSES[tone]}`;
  return (
    <Link to={href} aria-label={aria} title={aria} className={className}>
      {icon}
      <span>{label}</span>
      {value != null && value !== '' && <span className="opacity-80">{value}</span>}
    </Link>
  );
}
