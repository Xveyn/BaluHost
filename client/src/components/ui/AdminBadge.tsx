interface AdminBadgeProps {
  className?: string;
  size?: 'sm' | 'md';
}

export function AdminBadge({ className, size = 'sm' }: AdminBadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full bg-amber-500/15 border border-amber-500/40 text-amber-300 font-medium ${
        size === 'sm' ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-0.5 text-xs'
      } ${className ?? ''}`}
    >
      Admin
    </span>
  );
}
