import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

export interface ArticleMeta {
  title: string;
  slug: string;
  icon: string;
  version: string;
  order: number;
}

export interface Article extends ArticleMeta {
  content: string;
  category: 'setup' | 'wiki';
  lang: string;
}

/**
 * Parse frontmatter from a markdown string.
 * Returns { meta, content } where meta is the parsed YAML-like key-value pairs.
 */
function parseFrontmatter(raw: string): { meta: Record<string, string>; content: string } {
  const match = raw.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/);
  if (!match) return { meta: {}, content: raw };

  const meta: Record<string, string> = {};
  for (const line of match[1].split('\n')) {
    const idx = line.indexOf(':');
    if (idx > 0) {
      const key = line.slice(0, idx).trim();
      const val = line.slice(idx + 1).trim();
      meta[key] = val;
    }
  }
  return { meta, content: match[2] };
}

// Eagerly import all .md files as raw strings at build time.
// Vite resolves these at compile time — zero runtime cost.
const setupFiles = import.meta.glob('/src/content/manual/setup/*.md', { eager: true, query: '?raw', import: 'default' }) as Record<string, string>;
const wikiFiles = import.meta.glob('/src/content/manual/wiki/*.md', { eager: true, query: '?raw', import: 'default' }) as Record<string, string>;

function parseArticles(files: Record<string, string>, category: 'setup' | 'wiki'): Article[] {
  return Object.entries(files).map(([path, raw]) => {
    const { meta, content } = parseFrontmatter(raw);
    // Extract lang from filename: e.g. /src/content/manual/setup/vpn.de.md → "de"
    const filename = path.split('/').pop() ?? '';
    const langMatch = filename.match(/\.(\w+)\.md$/);
    const lang = langMatch ? langMatch[1] : 'de';

    return {
      title: meta.title ?? filename,
      slug: meta.slug ?? filename.replace(/\.\w+\.md$/, ''),
      icon: meta.icon ?? 'file-text',
      version: meta.version ?? '0.0.0',
      order: parseInt(meta.order ?? '99', 10),
      content,
      category,
      lang,
    };
  });
}

const allSetupArticles = parseArticles(setupFiles, 'setup');
const allWikiArticles = parseArticles(wikiFiles, 'wiki');

export function useManualContent() {
  const { i18n } = useTranslation();
  const lang = i18n.language?.split('-')[0] ?? 'de'; // "de-DE" → "de"

  return useMemo(() => {
    const filterByLang = (articles: Article[]) => {
      const forLang = articles.filter((a) => a.lang === lang);
      // Fallback to 'de' if no articles found for current language
      if (forLang.length === 0 && lang !== 'de') {
        return articles.filter((a) => a.lang === 'de');
      }
      return forLang;
    };

    const setup = filterByLang(allSetupArticles).sort((a, b) => a.order - b.order);
    const wiki = filterByLang(allWikiArticles).sort((a, b) => a.order - b.order);

    return { setup, wiki };
  }, [lang]);
}
