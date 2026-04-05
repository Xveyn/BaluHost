import * as Icons from 'lucide-react';

interface ArticleCardProps {
  title: string;
  icon: string;
  onClick: () => void;
}

/** Resolve a lucide icon name (e.g. "cloud-download") to a component */
function getLucideIcon(name: string): React.ReactNode {
  const pascal = name
    .split('-')
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join('');
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const IconComponent = (Icons as Record<string, any>)[pascal];
  if (IconComponent) return <IconComponent className="h-5 w-5" />;
  return <Icons.FileText className="h-5 w-5" />;
}

export default function ArticleCard({ title, icon, onClick }: ArticleCardProps) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left relative overflow-hidden rounded-2xl border border-slate-800/60 bg-slate-900/55 p-4 shadow-[0_20px_60px_rgba(2,6,23,0.55)] backdrop-blur-xl hover:border-slate-700/80 transition-all duration-200 group touch-manipulation active:scale-[0.99]"
    >
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-slate-800 bg-slate-950/60 text-sky-400 group-hover:border-sky-500/40 transition-colors flex-shrink-0">
          {getLucideIcon(icon)}
        </div>
        <div className="flex-1 min-w-0 pt-1">
          <h3 className="text-sm sm:text-base font-medium text-white truncate">
            {title}
          </h3>
        </div>
        <Icons.ChevronRight className="h-5 w-5 text-slate-600 group-hover:text-slate-400 transition-colors flex-shrink-0 mt-1.5" />
      </div>
    </button>
  );
}
