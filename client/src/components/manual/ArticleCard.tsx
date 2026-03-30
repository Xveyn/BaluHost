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
      className="w-full text-left bg-slate-800/40 backdrop-blur-sm rounded-xl border border-slate-700/50 p-4 hover:border-slate-600/50 hover:bg-slate-800/60 transition-all group touch-manipulation active:scale-[0.99]"
    >
      <div className="flex items-start gap-3">
        <div className="p-2 bg-cyan-500/20 rounded-lg text-cyan-400 group-hover:bg-cyan-500/30 transition-colors flex-shrink-0">
          {getLucideIcon(icon)}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm sm:text-base font-semibold text-white truncate">
            {title}
          </h3>
        </div>
        <Icons.ChevronRight className="h-5 w-5 text-slate-500 group-hover:text-slate-300 transition-colors flex-shrink-0 mt-0.5" />
      </div>
    </button>
  );
}
