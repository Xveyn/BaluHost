import { useTranslation } from 'react-i18next';
import { useManualContent } from '../../hooks/useManualContent';
import { useVersion } from '../../contexts/VersionContext';
import ArticleCard from './ArticleCard';
import ArticleView from './ArticleView';
import { FileText } from 'lucide-react';

interface WikiTabProps {
  selectedArticle: string | null;
  onSelectArticle: (slug: string | null) => void;
}

export default function WikiTab({ selectedArticle, onSelectArticle }: WikiTabProps) {
  const { t } = useTranslation('manual');
  const { wiki } = useManualContent();
  const { version } = useVersion();
  const appVersion = version ?? '0.0.0';

  const activeArticle = selectedArticle
    ? wiki.find((a) => a.slug === selectedArticle)
    : null;

  if (activeArticle) {
    return (
      <ArticleView
        article={activeArticle}
        appVersion={appVersion}
        onBack={() => onSelectArticle(null)}
      />
    );
  }

  if (wiki.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-slate-500">
        <FileText className="h-12 w-12 mb-3 opacity-40" />
        <p className="text-sm">{t('noArticles')}</p>
      </div>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {wiki.map((article) => (
        <ArticleCard
          key={article.slug}
          article={article}
          appVersion={appVersion}
          onClick={() => onSelectArticle(article.slug)}
        />
      ))}
    </div>
  );
}
