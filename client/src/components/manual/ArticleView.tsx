import Markdown from 'react-markdown';
import { ArrowLeft } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { Article } from '../../hooks/useManualContent';
import VersionBadge from './VersionBadge';

interface ArticleViewProps {
  article: Article;
  appVersion: string;
  onBack: () => void;
}

export default function ArticleView({ article, appVersion, onBack }: ArticleViewProps) {
  const { t } = useTranslation('manual');

  return (
    <div className="space-y-4">
      {/* Back button + version */}
      <div className="flex items-center justify-between">
        <button
          onClick={onBack}
          className="flex items-center gap-2 text-sm text-slate-400 hover:text-cyan-400 transition-colors touch-manipulation"
        >
          <ArrowLeft className="h-4 w-4" />
          {t('backToOverview')}
        </button>
        <VersionBadge articleVersion={article.version} appVersion={appVersion} />
      </div>

      {/* Markdown content */}
      <div className="bg-slate-800/40 backdrop-blur-sm rounded-xl border border-slate-700/50 p-4 sm:p-6">
        <article className="prose prose-invert prose-slate max-w-none prose-headings:text-white prose-h1:text-xl prose-h1:sm:text-2xl prose-h1:font-bold prose-h2:text-lg prose-h2:sm:text-xl prose-h2:font-semibold prose-h2:mt-6 prose-h2:mb-3 prose-h3:text-base prose-h3:font-semibold prose-p:text-slate-300 prose-p:text-sm prose-p:sm:text-base prose-p:leading-relaxed prose-li:text-slate-300 prose-li:text-sm prose-li:sm:text-base prose-strong:text-white prose-code:text-cyan-400 prose-code:bg-slate-900/60 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:sm:text-sm prose-pre:bg-slate-900/60 prose-pre:border prose-pre:border-slate-700/50 prose-pre:rounded-lg prose-a:text-cyan-400 prose-a:no-underline hover:prose-a:underline">
          <Markdown>{article.content}</Markdown>
        </article>
      </div>
    </div>
  );
}
