import { useTranslation } from 'react-i18next';
import { FileText, Loader2 } from 'lucide-react';
import type { DocsGroupInfo } from '../../hooks/useDocsIndex';
import { useDocsArticle } from '../../hooks/useDocsArticle';
import ArticleCard from './ArticleCard';
import ArticleView from './ArticleView';

interface DocsGroupTabProps {
  group: DocsGroupInfo;
  selectedArticle: string | null;
  onSelectArticle: (slug: string | null) => void;
}

export default function DocsGroupTab({ group, selectedArticle, onSelectArticle }: DocsGroupTabProps) {
  const { t } = useTranslation('manual');
  const { article, isLoading, error } = useDocsArticle(selectedArticle);

  if (selectedArticle) {
    if (isLoading) {
      return (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 text-cyan-400 animate-spin" />
        </div>
      );
    }
    if (error || !article) {
      return (
        <div className="flex flex-col items-center justify-center py-16 text-slate-500">
          <FileText className="h-12 w-12 mb-3 opacity-40" />
          <p className="text-sm">{error ?? t('errorLoading')}</p>
        </div>
      );
    }
    return (
      <ArticleView
        content={article.content}
        title={article.title}
        onBack={() => onSelectArticle(null)}
      />
    );
  }

  if (group.articles.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-slate-500">
        <FileText className="h-12 w-12 mb-3 opacity-40" />
        <p className="text-sm">{t('noArticles')}</p>
      </div>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {group.articles.map((a) => (
        <ArticleCard
          key={a.slug}
          title={a.title}
          icon={a.icon}
          onClick={() => onSelectArticle(a.slug)}
        />
      ))}
    </div>
  );
}
