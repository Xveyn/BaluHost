# User Manual Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the API Center page with a User Manual page containing Setup guides (Markdown), Wiki (Markdown), and API Reference (existing OpenAPI docs).

**Architecture:** Single `UserManualPage.tsx` with three tabs via query-params (`?tab=setup|wiki|api`). Markdown files per language under `client/src/content/manual/`, loaded at build-time via `import.meta.glob`. The existing API docs logic is extracted into `ApiReferenceTab.tsx` with no feature loss.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, react-markdown (new dep), Vite import.meta.glob, react-i18next

---

### Task 1: Install react-markdown dependency

**Files:**
- Modify: `client/package.json`

- [ ] **Step 1: Install react-markdown**

```bash
cd client && npm install react-markdown
```

- [ ] **Step 2: Verify installation**

```bash
cd client && node -e "require.resolve('react-markdown') && console.log('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add client/package.json client/package-lock.json
git commit -m "chore: add react-markdown dependency for User Manual"
```

---

### Task 2: Create i18n namespace `manual` (de + en)

**Files:**
- Create: `client/src/i18n/locales/de/manual.json`
- Create: `client/src/i18n/locales/en/manual.json`
- Modify: `client/src/i18n/index.ts`

- [ ] **Step 1: Create German manual.json**

Create `client/src/i18n/locales/de/manual.json`:

```json
{
  "title": "Benutzerhandbuch",
  "version": "Dokumentation für v{{version}}",
  "tabs": {
    "setup": "Setup",
    "wiki": "Wiki",
    "api": "API-Referenz"
  },
  "staleness": "Zuletzt geprüft für v{{version}}",
  "upToDate": "Aktuell für v{{version}}",
  "backToOverview": "Zurück zur Übersicht",
  "noArticles": "Noch keine Artikel vorhanden",
  "searchPlaceholder": "Artikel suchen..."
}
```

- [ ] **Step 2: Create English manual.json**

Create `client/src/i18n/locales/en/manual.json`:

```json
{
  "title": "User Manual",
  "version": "Documentation for v{{version}}",
  "tabs": {
    "setup": "Setup",
    "wiki": "Wiki",
    "api": "API Reference"
  },
  "staleness": "Last verified for v{{version}}",
  "upToDate": "Up to date for v{{version}}",
  "backToOverview": "Back to overview",
  "noArticles": "No articles yet",
  "searchPlaceholder": "Search articles..."
}
```

- [ ] **Step 3: Register namespace in i18n/index.ts**

In `client/src/i18n/index.ts`, add the imports after the existing `apiDocs` imports (line 34-35):

```typescript
import manualDe from './locales/de/manual.json';
import manualEn from './locales/en/manual.json';
```

Add to the `de` resource object (after `apiDocs: apiDocsDe,`):

```typescript
    manual: manualDe,
```

Add to the `en` resource object (after `apiDocs: apiDocsEn,`):

```typescript
    manual: manualEn,
```

Add `'manual'` to the `ns` array in the init config (line 81):

```typescript
ns: ['common', 'dashboard', 'fileManager', 'settings', 'admin', 'login', 'system', 'shares', 'plugins', 'devices', 'scheduler', 'notifications', 'updates', 'remoteServers', 'apiDocs', 'manual'],
```

- [ ] **Step 4: Update navigation keys in common.json (de)**

In `client/src/i18n/locales/de/common.json`, replace lines 89-90:

Old:
```json
    "apiCenter": "API-Center",
    "apiCenterDesc": "Docs & Limits",
```

New:
```json
    "apiCenter": "API-Center",
    "apiCenterDesc": "Docs & Limits",
    "userManual": "Benutzerhandbuch",
    "userManualDesc": "Setup, Wiki & API",
```

- [ ] **Step 5: Update navigation keys in common.json (en)**

In `client/src/i18n/locales/en/common.json`, replace lines 89-90:

Old:
```json
    "apiCenter": "API Center",
    "apiCenterDesc": "Docs & Limits",
```

New:
```json
    "apiCenter": "API Center",
    "apiCenterDesc": "Docs & Limits",
    "userManual": "User Manual",
    "userManualDesc": "Setup, Wiki & API",
```

- [ ] **Step 6: Commit**

```bash
git add client/src/i18n/
git commit -m "feat(i18n): add manual namespace and userManual navigation keys"
```

---

### Task 3: Create `useManualContent` hook

**Files:**
- Create: `client/src/hooks/useManualContent.ts`

This hook loads all Markdown files from `client/src/content/manual/` via `import.meta.glob`, parses frontmatter, and filters by current language.

- [ ] **Step 1: Create the hook**

Create `client/src/hooks/useManualContent.ts`:

```typescript
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
```

- [ ] **Step 2: Create content directories with a placeholder file to ensure they exist**

```bash
mkdir -p "client/src/content/manual/setup"
mkdir -p "client/src/content/manual/wiki"
```

Create a placeholder `client/src/content/manual/setup/cloud-import.de.md`:

```markdown
---
title: Cloud Import einrichten
slug: cloud-import
icon: cloud-download
version: 1.20.5
order: 1
---

# Cloud Import einrichten

Hier wird beschrieben, wie du OAuth für Google Drive, OneDrive oder iCloud konfigurierst, um Dateien in BaluHost zu importieren.

## Voraussetzungen

- Admin-Zugang zu BaluHost
- rclone muss auf dem Server installiert sein

## Schritte

1. Navigiere zu **Cloud Import** in der Seitenleiste
2. Klicke auf **Verbindung hinzufügen**
3. Wähle den gewünschten Cloud-Anbieter
4. Folge dem OAuth-Autorisierungsprozess im Browser
5. Nach erfolgreicher Autorisierung erscheint die Verbindung in der Übersicht
```

Create `client/src/content/manual/setup/cloud-import.en.md`:

```markdown
---
title: Set Up Cloud Import
slug: cloud-import
icon: cloud-download
version: 1.20.5
order: 1
---

# Set Up Cloud Import

This guide explains how to configure OAuth for Google Drive, OneDrive, or iCloud to import files into BaluHost.

## Prerequisites

- Admin access to BaluHost
- rclone must be installed on the server

## Steps

1. Navigate to **Cloud Import** in the sidebar
2. Click **Add Connection**
3. Select the desired cloud provider
4. Follow the OAuth authorization process in your browser
5. After successful authorization, the connection appears in the overview
```

- [ ] **Step 3: Commit**

```bash
git add client/src/hooks/useManualContent.ts client/src/content/
git commit -m "feat(manual): add useManualContent hook and initial cloud-import article"
```

---

### Task 4: Create shared components — `VersionBadge`, `ArticleCard`, `ArticleView`

**Files:**
- Create: `client/src/components/manual/VersionBadge.tsx`
- Create: `client/src/components/manual/ArticleCard.tsx`
- Create: `client/src/components/manual/ArticleView.tsx`

- [ ] **Step 1: Create VersionBadge component**

Create `client/src/components/manual/VersionBadge.tsx`:

```tsx
import { useTranslation } from 'react-i18next';

interface VersionBadgeProps {
  /** The version the article was last verified for */
  articleVersion: string;
  /** The current app version */
  appVersion: string;
}

/** Compare semver-like version strings: returns true if a >= b */
function isVersionCurrent(articleVer: string, appVer: string): boolean {
  const parse = (v: string) => v.replace(/^v/, '').split('.').map(Number);
  const a = parse(articleVer);
  const b = parse(appVer);
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    if ((a[i] ?? 0) < (b[i] ?? 0)) return false;
    if ((a[i] ?? 0) > (b[i] ?? 0)) return true;
  }
  return true; // equal
}

export default function VersionBadge({ articleVersion, appVersion }: VersionBadgeProps) {
  const { t } = useTranslation('manual');
  const current = isVersionCurrent(articleVersion, appVersion);

  if (current) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
        v{articleVersion}
      </span>
    );
  }

  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono bg-amber-500/15 text-amber-400 border border-amber-500/30"
      title={t('staleness', { version: articleVersion })}
    >
      v{articleVersion}
    </span>
  );
}
```

- [ ] **Step 2: Create ArticleCard component**

Create `client/src/components/manual/ArticleCard.tsx`:

```tsx
import * as Icons from 'lucide-react';
import type { Article } from '../../hooks/useManualContent';
import VersionBadge from './VersionBadge';

interface ArticleCardProps {
  article: Article;
  appVersion: string;
  onClick: () => void;
}

/** Resolve a lucide icon name (e.g. "cloud-download") to a component */
function getLucideIcon(name: string): React.ReactNode {
  // Convert kebab-case to PascalCase: "cloud-download" → "CloudDownload"
  const pascal = name
    .split('-')
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join('');
  const IconComponent = (Icons as Record<string, React.ComponentType<{ className?: string }>>)[pascal];
  if (IconComponent) return <IconComponent className="h-5 w-5" />;
  return <Icons.FileText className="h-5 w-5" />;
}

export default function ArticleCard({ article, appVersion, onClick }: ArticleCardProps) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left bg-slate-800/40 backdrop-blur-sm rounded-xl border border-slate-700/50 p-4 hover:border-slate-600/50 hover:bg-slate-800/60 transition-all group touch-manipulation active:scale-[0.99]"
    >
      <div className="flex items-start gap-3">
        <div className="p-2 bg-cyan-500/20 rounded-lg text-cyan-400 group-hover:bg-cyan-500/30 transition-colors flex-shrink-0">
          {getLucideIcon(article.icon)}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-sm sm:text-base font-semibold text-white truncate">
              {article.title}
            </h3>
            <VersionBadge articleVersion={article.version} appVersion={appVersion} />
          </div>
        </div>
        <Icons.ChevronRight className="h-5 w-5 text-slate-500 group-hover:text-slate-300 transition-colors flex-shrink-0 mt-0.5" />
      </div>
    </button>
  );
}
```

- [ ] **Step 3: Create ArticleView component**

Create `client/src/components/manual/ArticleView.tsx`:

```tsx
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
```

- [ ] **Step 4: Commit**

```bash
git add client/src/components/manual/
git commit -m "feat(manual): add VersionBadge, ArticleCard, and ArticleView components"
```

---

### Task 5: Create `SetupTab` and `WikiTab`

**Files:**
- Create: `client/src/components/manual/SetupTab.tsx`
- Create: `client/src/components/manual/WikiTab.tsx`

- [ ] **Step 1: Create SetupTab**

Create `client/src/components/manual/SetupTab.tsx`:

```tsx
import { useTranslation } from 'react-i18next';
import { useManualContent } from '../../hooks/useManualContent';
import { useVersion } from '../../contexts/VersionContext';
import ArticleCard from './ArticleCard';
import ArticleView from './ArticleView';
import { FileText } from 'lucide-react';

interface SetupTabProps {
  selectedArticle: string | null;
  onSelectArticle: (slug: string | null) => void;
}

export default function SetupTab({ selectedArticle, onSelectArticle }: SetupTabProps) {
  const { t } = useTranslation('manual');
  const { setup } = useManualContent();
  const { version } = useVersion();
  const appVersion = version ?? '0.0.0';

  const activeArticle = selectedArticle
    ? setup.find((a) => a.slug === selectedArticle)
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

  if (setup.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-slate-500">
        <FileText className="h-12 w-12 mb-3 opacity-40" />
        <p className="text-sm">{t('noArticles')}</p>
      </div>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {setup.map((article) => (
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
```

- [ ] **Step 2: Create WikiTab**

Create `client/src/components/manual/WikiTab.tsx`:

```tsx
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
```

- [ ] **Step 3: Commit**

```bash
git add client/src/components/manual/SetupTab.tsx client/src/components/manual/WikiTab.tsx
git commit -m "feat(manual): add SetupTab and WikiTab components"
```

---

### Task 6: Extract `ApiReferenceTab` from `ApiCenterPage`

**Files:**
- Create: `client/src/components/manual/ApiReferenceTab.tsx`

This component extracts the entire API documentation and rate-limits UI from the existing `ApiCenterPage.tsx`. It receives `isAdmin`, `user`, and `token` as props (loaded by the parent page).

- [ ] **Step 1: Create ApiReferenceTab.tsx**

Create `client/src/components/manual/ApiReferenceTab.tsx`. This is a refactored extraction from `ApiCenterPage.tsx` lines 24-604.

```tsx
import { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Code,
  Shield,
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
  Zap,
  Search,
  RefreshCw,
  AlertTriangle,
  Gauge,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { buildApiUrl } from '../../lib/api';
import { methodColors } from '../../data/api-endpoints';
import type { ApiEndpoint } from '../../data/api-endpoints';
import { useOpenApiSchema } from '../../hooks/useOpenApiSchema';
import { RateLimitsTab } from '../../components/rate-limits';

// ==================== Types ====================

interface RateLimitConfig {
  id: number;
  endpoint_type: string;
  limit_string: string;
  description: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string | null;
  updated_by: number | null;
}

// ==================== Dynamic Rate Limit Matching ====================

function matchEndpointToRateLimitType(method: string, path: string): string | null {
  const p = path.toLowerCase();
  const m = method.toUpperCase();

  if (m === 'POST' && p === '/api/auth/login') return 'auth_login';
  if (m === 'POST' && p === '/api/auth/register') return 'auth_register';
  if (m === 'POST' && p === '/api/auth/change-password') return 'auth_password_change';
  if (m === 'POST' && p === '/api/auth/refresh') return 'auth_refresh';
  if (m === 'POST' && p === '/api/auth/verify-2fa') return 'auth_2fa_verify';
  if (m === 'POST' && p.startsWith('/api/auth/2fa/')) return 'auth_2fa_setup';
  if (p.startsWith('/api/auth/')) return 'user_operations';

  if (p.startsWith('/api/files/upload/chunked')) return 'file_chunked';
  if (m === 'POST' && p.startsWith('/api/files/upload')) return 'file_upload';
  if (m === 'GET' && p.startsWith('/api/files/download')) return 'file_download';
  if (m === 'GET' && p.startsWith('/api/files/list')) return 'file_list';
  if (m === 'DELETE' && p.startsWith('/api/files/')) return 'file_delete';
  if (p.startsWith('/api/files/')) return 'file_write';

  if (p.startsWith('/api/activity/')) return 'file_list';

  if (['POST', 'PATCH', 'DELETE'].includes(m) && p.startsWith('/api/shares')) return 'share_create';
  if (p.startsWith('/api/shares')) return 'share_list';

  if (m === 'POST' && (p === '/api/mobile/register' || p === '/api/mobile/token/generate')) return 'mobile_register';
  if (p.includes('/mobile/sync') || p.includes('/mobile/upload-queue')) return 'mobile_sync';

  if (p.includes('/desktop-pairing/device-code')) return 'desktop_pairing_request';
  if (p.includes('/desktop-pairing/token')) return 'desktop_pairing_poll';
  if (p.includes('/desktop-pairing/verify')) return 'desktop_pairing_verify';
  if (p.includes('/desktop-pairing/approve')) return 'desktop_pairing_approve';

  if (p.startsWith('/api/vpn/') || p === '/api/vpn') return 'vpn_operations';
  if (p.startsWith('/api/backup/') || p === '/api/backup') return 'backup_operations';
  if (p.startsWith('/api/sync/')) return 'sync_operations';

  if (m === 'POST' && p.includes('/benchmark/run')) return 'admin_benchmark';

  if (p.startsWith('/api/api-keys')) return 'api_key_operations';

  if (p.startsWith('/api/users')) return 'user_operations';

  if (p.startsWith('/api/system/') || p.startsWith('/api/monitoring/') || p.startsWith('/api/energy/')) {
    return m === 'GET' ? 'system_monitor' : 'admin_operations';
  }

  if (p.startsWith('/api/vcl/')) return m === 'GET' ? 'file_list' : 'file_write';

  if (p.startsWith('/api/ssd-cache/')) return m === 'GET' ? 'file_list' : 'admin_operations';

  const adminPrefixes = [
    '/api/admin/', '/api/admin-db/', '/api/schedulers/', '/api/fans/',
    '/api/power/', '/api/pihole/', '/api/sleep/', '/api/cloud/',
    '/api/updates/', '/api/samba/', '/api/webdav/', '/api/plugins/',
    '/api/notifications/', '/api/benchmark/', '/api/smart-devices/',
  ];
  if (adminPrefixes.some(prefix => p.startsWith(prefix))) return 'admin_operations';

  return null;
}

// ==================== Endpoint Card Component ====================

interface EndpointCardProps {
  endpoint: ApiEndpoint;
  rateLimits: Record<string, RateLimitConfig>;
  t: (key: string) => string;
}

function EndpointCard({ endpoint, rateLimits, t }: EndpointCardProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const rateLimitKey = matchEndpointToRateLimitType(endpoint.method, endpoint.path);
  const rateLimit = rateLimitKey ? rateLimits[rateLimitKey] : null;

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-slate-800/40 backdrop-blur-sm rounded-xl border border-slate-700/50 p-3 sm:p-4 hover:border-slate-600/50 transition-all">
      <div
        className="flex items-center justify-between cursor-pointer touch-manipulation"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-3 flex-1 min-w-0">
          <span className={`px-2 sm:px-3 py-1 rounded-lg text-[10px] sm:text-xs font-bold border flex-shrink-0 ${methodColors[endpoint.method]}`}>
            {endpoint.method}
          </span>
          <code className="text-cyan-400 font-mono text-xs sm:text-sm truncate">{endpoint.path}</code>
          <span className="text-slate-400 text-xs sm:text-sm hidden lg:inline truncate">{endpoint.description}</span>
          {endpoint.requiresAuth && (
            <span title={t('system:apiCenter.authRequired')} className="flex-shrink-0"><Shield className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-amber-400" /></span>
          )}
          {rateLimit && (
            <span
              className={`px-1.5 sm:px-2 py-0.5 rounded text-[10px] sm:text-xs font-mono flex-shrink-0 ${
                rateLimit.enabled
                  ? 'bg-emerald-500/20 text-emerald-400'
                  : 'bg-slate-500/20 text-slate-500'
              }`}
              title={`Rate limit: ${rateLimit.limit_string}`}
            >
              <Zap className="w-2.5 h-2.5 sm:w-3 sm:h-3 inline mr-0.5 sm:mr-1" />
              <span className="hidden sm:inline">{rateLimit.limit_string}</span>
            </span>
          )}
        </div>
        <div className="flex items-center gap-1 sm:gap-2 flex-shrink-0 ml-2">
          {isOpen ? (
            <ChevronDown className="w-5 h-5 text-slate-400" />
          ) : (
            <ChevronRight className="w-5 h-5 text-slate-400" />
          )}
        </div>
      </div>

      {isOpen && (
        <div className="mt-3 sm:mt-4 space-y-3 sm:space-y-4 border-t border-slate-700/50 pt-3 sm:pt-4">
          <p className="text-slate-300 text-xs sm:text-sm lg:hidden">{endpoint.description}</p>

          {endpoint.params && endpoint.params.length > 0 && (
            <div>
              <h4 className="text-xs sm:text-sm font-semibold text-slate-300 mb-2">{t('system:apiCenter.parameters')}</h4>
              <div className="space-y-1.5 sm:space-y-2">
                {endpoint.params.map((param, idx) => (
                  <div key={idx} className="flex items-start gap-2 sm:gap-3 text-xs sm:text-sm flex-wrap">
                    <code className="text-cyan-400 font-mono">{param.name}</code>
                    <span className="text-slate-500">({param.type})</span>
                    {param.required && <span className="text-red-400 text-[10px] sm:text-xs">{t('system:apiCenter.required')}</span>}
                    <span className="text-slate-400 w-full sm:w-auto">{param.description}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {endpoint.body && endpoint.body.length > 0 && (
            <div>
              <h4 className="text-xs sm:text-sm font-semibold text-slate-300 mb-2">{t('system:apiCenter.requestBody')}</h4>
              <div className="space-y-1.5 sm:space-y-2">
                {endpoint.body.map((field, idx) => (
                  <div key={idx} className="flex items-start gap-2 sm:gap-3 text-xs sm:text-sm flex-wrap">
                    <code className="text-violet-400 font-mono">{field.field}</code>
                    <span className="text-slate-500">({field.type})</span>
                    {field.required && <span className="text-red-400 text-[10px] sm:text-xs">{t('system:apiCenter.required')}</span>}
                    <span className="text-slate-400 w-full sm:w-auto">{field.description}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {endpoint.response && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-xs sm:text-sm font-semibold text-slate-300">{t('system:apiCenter.response')}</h4>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    copyToClipboard(endpoint.response!);
                  }}
                  className="text-slate-400 hover:text-cyan-400 transition-colors p-2 -mr-2 touch-manipulation active:scale-95 min-w-[36px] min-h-[36px] flex items-center justify-center"
                >
                  {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
                </button>
              </div>
              <pre className="bg-slate-900/60 border border-slate-700/50 rounded-lg p-2 sm:p-3 text-[10px] sm:text-xs overflow-x-auto max-w-full">
                <code className="text-slate-300">{endpoint.response}</code>
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ==================== Main Component ====================

interface ApiReferenceTabProps {
  isAdmin: boolean;
  token: string | null;
}

export default function ApiReferenceTab({ isAdmin, token }: ApiReferenceTabProps) {
  const { t } = useTranslation(['system', 'common']);
  const [activeView, setActiveView] = useState<'docs' | 'limits'>('docs');
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedSection, setSelectedSection] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [rateLimits, setRateLimits] = useState<Record<string, RateLimitConfig>>({});
  const [loading, setLoading] = useState(true);

  const { sections: apiSections, categories: apiCategories, loading: schemaLoading, error: schemaError, refetch: refetchSchema } = useOpenApiSchema();

  const getApiBaseUrl = (): string => {
    const hostname = window.location.hostname;
    const isDev = import.meta.env.DEV;
    const port = isDev ? 3001 : 8000;
    const protocol = window.location.protocol;
    return `${protocol}//${hostname}:${port}`;
  };

  const apiBaseUrl = getApiBaseUrl();

  useEffect(() => {
    if (isAdmin) {
      loadRateLimits();
    } else {
      setLoading(false);
    }
  }, [isAdmin]);

  const loadRateLimits = async () => {
    if (!token) {
      setLoading(false);
      return;
    }

    try {
      const response = await fetch(buildApiUrl('/api/admin/rate-limits'), {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        const map: Record<string, RateLimitConfig> = {};
        data.configs.forEach((c: RateLimitConfig) => {
          map[c.endpoint_type] = c;
        });
        setRateLimits(map);
      }
    } catch {
      // Rate limits not available
    } finally {
      setLoading(false);
    }
  };

  const visibleSections = useMemo(() => {
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return apiSections
        .map(s => ({
          ...s,
          endpoints: s.endpoints.filter(e =>
            e.path.toLowerCase().includes(q) ||
            e.description.toLowerCase().includes(q)
          ),
        }))
        .filter(s => s.endpoints.length > 0);
    }

    const categorySections = selectedCategory
      ? apiCategories.find(c => c.id === selectedCategory)?.sections ?? []
      : apiSections;

    return selectedSection
      ? categorySections.filter(s => s.title === selectedSection)
      : categorySections;
  }, [searchQuery, selectedCategory, selectedSection, apiSections, apiCategories]);

  const currentCategorySections = selectedCategory
    ? apiCategories.find(c => c.id === selectedCategory)?.sections ?? []
    : [];

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* View Toggle (admin: API Docs | Rate Limits) */}
      {isAdmin && (
        <div className="flex gap-2">
          <button
            onClick={() => setActiveView('docs')}
            className={`flex items-center gap-2 rounded-xl px-4 py-2 sm:py-2.5 text-sm sm:text-base font-semibold transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
              activeView === 'docs'
                ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40 shadow-lg shadow-cyan-500/10'
                : 'bg-slate-800/40 text-slate-400 hover:bg-slate-800/60 hover:text-slate-300 border border-slate-700/40'
            }`}
          >
            <Code className="w-4 h-4" />
            <span>{t('system:apiCenter.tabs.apiDocs')}</span>
          </button>
          <button
            onClick={() => setActiveView('limits')}
            className={`flex items-center gap-2 rounded-xl px-4 py-2 sm:py-2.5 text-sm sm:text-base font-semibold transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
              activeView === 'limits'
                ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40 shadow-lg shadow-amber-500/10'
                : 'bg-slate-800/40 text-slate-400 hover:bg-slate-800/60 hover:text-slate-300 border border-slate-700/40'
            }`}
          >
            <Gauge className="w-4 h-4" />
            <span>{t('system:apiCenter.tabs.rateLimits')}</span>
          </button>
        </div>
      )}

      {/* Rate Limits View */}
      {activeView === 'limits' && isAdmin && <RateLimitsTab />}

      {/* API Docs View */}
      {activeView === 'docs' && <>
        {/* Schema Error */}
        {schemaError && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4">
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0" />
              <div className="flex-1">
                <p className="text-sm text-red-300">API schema could not be loaded: {schemaError}</p>
              </div>
              <button
                onClick={refetchSchema}
                className="px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white rounded-lg transition-colors text-sm font-medium"
              >
                Retry
              </button>
            </div>
          </div>
        )}

        {/* Base URL Info */}
        <div className="bg-cyan-500/10 border border-cyan-500/30 rounded-xl p-3 sm:p-4">
          <div className="flex items-start gap-2 sm:gap-3">
            <Code className="w-4 h-4 sm:w-5 sm:h-5 text-cyan-400 mt-0.5 flex-shrink-0" />
            <div className="min-w-0 flex-1">
              <h3 className="font-semibold text-white text-sm sm:text-base mb-1">{t('system:apiCenter.baseUrl')}</h3>
              <div className="flex items-center gap-2">
                <code className="text-xs sm:text-sm text-cyan-400 bg-slate-900/60 px-2 sm:px-3 py-1 rounded block overflow-x-auto flex-1">
                  {apiBaseUrl}
                </code>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(apiBaseUrl);
                    toast.success(t('system:apiCenter.baseUrlCopied'));
                  }}
                  className="p-2 bg-slate-700/50 hover:bg-slate-700 rounded-lg transition-colors flex-shrink-0 touch-manipulation active:scale-95"
                  title={t('system:apiCenter.baseUrl')}
                >
                  <Copy className="w-4 h-4 text-slate-300" />
                </button>
              </div>
              <p className="text-xs sm:text-sm text-slate-400 mt-2">
                <span className="hidden sm:inline">{t('system:apiCenter.authRequiredNote')} </span>
                <code className="text-[10px] sm:text-xs text-slate-300 bg-slate-900/60 px-1.5 sm:px-2 py-0.5 rounded sm:ml-2 block sm:inline mt-1 sm:mt-0 overflow-x-auto">
                  Authorization: Bearer {"<token>"}
                </code>
              </p>
            </div>
          </div>
        </div>

        {/* Search Field */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('system:apiCenter.searchPlaceholder', 'Search endpoints...')}
            className="w-full pl-10 pr-4 py-2.5 bg-slate-800/40 border border-slate-700/50 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/30 transition-all"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white transition-colors text-xs"
            >
              ✕
            </button>
          )}
        </div>

        {/* Refresh button */}
        <div className="flex justify-end">
          <button
            onClick={refetchSchema}
            className="p-2 bg-slate-800/40 hover:bg-slate-700/60 border border-slate-700/50 rounded-lg transition-colors touch-manipulation active:scale-95"
            title="Refresh API schema"
          >
            <RefreshCw className={`w-4 h-4 text-slate-400 ${schemaLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {/* Category Tabs */}
        {!searchQuery.trim() && (
          <div className="space-y-3">
            <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 scrollbar-none">
              <div className="flex gap-2 min-w-max sm:min-w-0 sm:flex-wrap">
                <button
                  onClick={() => { setSelectedCategory(null); setSelectedSection(null); }}
                  className={`flex items-center gap-2 rounded-xl px-4 py-2 sm:py-2.5 text-sm sm:text-base font-semibold transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
                    !selectedCategory
                      ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40 shadow-lg shadow-blue-500/10'
                      : 'bg-slate-800/40 text-slate-400 hover:bg-slate-800/60 hover:text-slate-300 border border-slate-700/40'
                  }`}
                >
                  <span>{t('system:apiCenter.all')}</span>
                  <span className="text-[10px] opacity-70">({apiSections.reduce((sum, s) => sum + s.endpoints.length, 0)})</span>
                </button>
                {apiCategories.map((cat) => {
                  const endpointCount = cat.sections.reduce((sum, s) => sum + s.endpoints.length, 0);
                  return (
                    <button
                      key={cat.id}
                      onClick={() => { setSelectedCategory(cat.id); setSelectedSection(null); }}
                      className={`flex items-center gap-2 rounded-xl px-4 py-2 sm:py-2.5 text-sm sm:text-base font-semibold transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
                        selectedCategory === cat.id
                          ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40 shadow-lg shadow-blue-500/10'
                          : 'bg-slate-800/40 text-slate-400 hover:bg-slate-800/60 hover:text-slate-300 border border-slate-700/40'
                      }`}
                    >
                      <span>{cat.label}</span>
                      <span className="text-[10px] opacity-70">({endpointCount})</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {selectedCategory && currentCategorySections.length > 0 && (
              <div className="relative">
                <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 scrollbar-none">
                  <div className="flex gap-2 border-b border-slate-800 pb-3 min-w-max sm:min-w-0 sm:flex-wrap">
                    <button
                      onClick={() => setSelectedSection(null)}
                      className={`flex items-center gap-2 rounded-lg px-3 sm:px-4 py-2 sm:py-2.5 text-xs sm:text-sm font-medium transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
                        !selectedSection
                          ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                          : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-300 border border-transparent'
                      }`}
                    >
                      <span>{t('system:apiCenter.all')}</span>
                    </button>
                    {currentCategorySections.map((section) => (
                      <button
                        key={section.title}
                        onClick={() => setSelectedSection(section.title)}
                        className={`flex items-center gap-2 rounded-lg px-3 sm:px-4 py-2 sm:py-2.5 text-xs sm:text-sm font-medium transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
                          selectedSection === section.title
                            ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                            : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-300 border border-transparent'
                        }`}
                      >
                        {section.icon}
                        <span>{section.title}</span>
                        <span className="text-[10px] opacity-70">({section.endpoints.length})</span>
                      </button>
                    ))}
                  </div>
                </div>
                <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-slate-950 to-transparent sm:hidden" />
              </div>
            )}
          </div>
        )}

        {/* Loading State */}
        {(loading || schemaLoading) && (
          <div className="space-y-4">
            {[1, 2, 3].map(i => (
              <div key={i} className="animate-pulse">
                <div className="h-6 bg-slate-800/60 rounded w-48 mb-3" />
                <div className="space-y-2">
                  <div className="h-14 bg-slate-800/40 rounded-xl" />
                  <div className="h-14 bg-slate-800/40 rounded-xl" />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* API Sections */}
        {!loading && !schemaLoading && visibleSections.map((section) => (
          <div key={section.title}>
            <div className="flex items-center gap-2 sm:gap-3 mb-3 sm:mb-4">
              <div className="p-1.5 sm:p-2 bg-cyan-500/20 rounded-lg text-cyan-400">
                {section.icon}
              </div>
              <h2 className="text-lg sm:text-xl font-bold text-white">{section.title}</h2>
            </div>
            <div className="space-y-2 sm:space-y-3">
              {section.endpoints.map((endpoint, idx) => (
                <EndpointCard
                  key={idx}
                  endpoint={endpoint}
                  rateLimits={rateLimits}
                  t={t}
                />
              ))}
            </div>
          </div>
        ))}
      </>}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/components/manual/ApiReferenceTab.tsx
git commit -m "feat(manual): extract ApiReferenceTab from ApiCenterPage"
```

---

### Task 7: Create `UserManualPage.tsx`

**Files:**
- Create: `client/src/pages/UserManualPage.tsx`

- [ ] **Step 1: Create UserManualPage.tsx**

Create `client/src/pages/UserManualPage.tsx`:

```tsx
import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { BookOpen, Wrench, Library, Code } from 'lucide-react';
import { useVersion } from '../contexts/VersionContext';
import { useAuth } from '../contexts/AuthContext';
import SetupTab from '../components/manual/SetupTab';
import WikiTab from '../components/manual/WikiTab';
import ApiReferenceTab from '../components/manual/ApiReferenceTab';

type TabType = 'setup' | 'wiki' | 'api';

const VALID_TABS = new Set<TabType>(['setup', 'wiki', 'api']);

const TAB_CONFIG: { id: TabType; labelKey: string; icon: React.ReactNode }[] = [
  { id: 'setup', labelKey: 'manual:tabs.setup', icon: <Wrench className="h-4 w-4" /> },
  { id: 'wiki', labelKey: 'manual:tabs.wiki', icon: <Library className="h-4 w-4" /> },
  { id: 'api', labelKey: 'manual:tabs.api', icon: <Code className="h-4 w-4" /> },
];

export default function UserManualPage() {
  const { t } = useTranslation(['manual', 'system', 'common']);
  const { version } = useVersion();
  const { user, token, isAdmin } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  const rawTab = searchParams.get('tab') || 'setup';
  const activeTab = (VALID_TABS.has(rawTab as TabType) ? rawTab : 'setup') as TabType;
  const selectedArticle = searchParams.get('article') || null;

  const handleTabChange = (tab: TabType) => {
    setSearchParams({ tab });
  };

  const handleSelectArticle = (slug: string | null) => {
    if (slug) {
      setSearchParams({ tab: activeTab, article: slug });
    } else {
      setSearchParams({ tab: activeTab });
    }
  };

  return (
    <div className="space-y-4 sm:space-y-6 p-4 sm:p-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl lg:text-3xl font-bold bg-gradient-to-r from-cyan-400 via-blue-400 to-violet-400 bg-clip-text text-transparent flex items-center gap-2 sm:gap-3">
            <BookOpen className="w-6 h-6 sm:w-8 sm:h-8 text-cyan-400" />
            {t('manual:title')}
          </h1>
          <p className="text-slate-400 text-xs sm:text-sm mt-1">
            {t('manual:version', { version: version ?? '...' })}
          </p>
        </div>
        {/* Global version badge */}
        {version && (
          <span className="self-start sm:self-center inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-mono bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
            v{version}
          </span>
        )}
      </div>

      {/* Tab Navigation */}
      <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 scrollbar-none">
        <div className="flex gap-2 min-w-max sm:min-w-0 sm:flex-wrap">
          {TAB_CONFIG.map((tab) => (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id)}
              className={`flex items-center gap-2 rounded-xl px-4 py-2 sm:py-2.5 text-sm sm:text-base font-semibold transition-all whitespace-nowrap touch-manipulation active:scale-95 ${
                activeTab === tab.id
                  ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40 shadow-lg shadow-blue-500/10'
                  : 'bg-slate-800/40 text-slate-400 hover:bg-slate-800/60 hover:text-slate-300 border border-slate-700/40'
              }`}
            >
              {tab.icon}
              <span>{t(tab.labelKey)}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      {activeTab === 'setup' && (
        <SetupTab selectedArticle={selectedArticle} onSelectArticle={handleSelectArticle} />
      )}
      {activeTab === 'wiki' && (
        <WikiTab selectedArticle={selectedArticle} onSelectArticle={handleSelectArticle} />
      )}
      {activeTab === 'api' && (
        <ApiReferenceTab isAdmin={isAdmin} token={token} />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/pages/UserManualPage.tsx
git commit -m "feat(manual): add UserManualPage with three-tab layout"
```

---

### Task 8: Update routing (App.tsx) and navigation (Layout.tsx)

**Files:**
- Modify: `client/src/App.tsx`
- Modify: `client/src/components/Layout.tsx`

- [ ] **Step 1: Update App.tsx — change lazy import**

In `client/src/App.tsx`, replace line 40:

Old:
```tsx
const ApiCenterPage = isDesktop ? lazyWithRetry(() => import('./pages/ApiCenterPage')) : null;
```

New:
```tsx
const UserManualPage = isDesktop ? lazyWithRetry(() => import('./pages/UserManualPage')) : null;
```

- [ ] **Step 2: Update App.tsx — change route and add redirect**

In `client/src/App.tsx`, replace line 213:

Old:
```tsx
        {ApiCenterPage && <Route path="/docs" element={user ? <Layout><ApiCenterPage /></Layout> : <Navigate to="/login" />} />}
```

New:
```tsx
        {UserManualPage && <Route path="/manual" element={user ? <Layout><UserManualPage /></Layout> : <Navigate to="/login" />} />}
        {isDesktop && <Route path="/docs" element={<Navigate to="/manual" replace />} />}
```

- [ ] **Step 3: Update Layout.tsx — change nav entry**

In `client/src/components/Layout.tsx`, replace lines 210-214:

Old:
```tsx
    {
      path: '/docs',
      label: t('navigation.apiCenter'),
      description: t('navigation.apiCenterDesc'),
      icon: navIcon.docs
    },
```

New:
```tsx
    {
      path: '/manual',
      label: t('navigation.userManual'),
      description: t('navigation.userManualDesc'),
      icon: navIcon.docs
    },
```

- [ ] **Step 4: Verify build compiles**

```bash
cd client && npm run build
```

Expected: Build succeeds with no errors.

- [ ] **Step 5: Commit**

```bash
git add client/src/App.tsx client/src/components/Layout.tsx
git commit -m "feat(manual): wire up UserManualPage route and navigation"
```

---

### Task 9: Delete old `ApiCenterPage.tsx`

**Files:**
- Delete: `client/src/pages/ApiCenterPage.tsx`

- [ ] **Step 1: Delete the old page**

```bash
rm client/src/pages/ApiCenterPage.tsx
```

- [ ] **Step 2: Verify no remaining imports reference ApiCenterPage**

```bash
cd client && grep -r "ApiCenterPage" src/ --include="*.ts" --include="*.tsx"
```

Expected: No results (the lazy import was already changed in Task 8).

- [ ] **Step 3: Verify build still works**

```bash
cd client && npm run build
```

Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add -u client/src/pages/ApiCenterPage.tsx
git commit -m "refactor(manual): remove old ApiCenterPage (replaced by UserManualPage)"
```

---

### Task 10: Add remaining setup article placeholders

**Files:**
- Create: `client/src/content/manual/setup/vpn.de.md`
- Create: `client/src/content/manual/setup/vpn.en.md`
- Create: `client/src/content/manual/setup/mobile.de.md`
- Create: `client/src/content/manual/setup/mobile.en.md`
- Create: `client/src/content/manual/setup/desktop-sync.de.md`
- Create: `client/src/content/manual/setup/desktop-sync.en.md`
- Create: `client/src/content/manual/setup/pihole.de.md`
- Create: `client/src/content/manual/setup/pihole.en.md`
- Create: `client/src/content/manual/setup/smart-devices.de.md`
- Create: `client/src/content/manual/setup/smart-devices.en.md`
- Create: `client/src/content/manual/setup/notifications.de.md`
- Create: `client/src/content/manual/setup/notifications.en.md`
- Create: `client/src/content/manual/setup/samba.de.md`
- Create: `client/src/content/manual/setup/samba.en.md`
- Create: `client/src/content/manual/setup/webdav.de.md`
- Create: `client/src/content/manual/setup/webdav.en.md`

Each article follows the same frontmatter pattern. Content can be brief initially — the structure matters more than completeness at this stage.

- [ ] **Step 1: Create all German setup articles**

Create each file with proper frontmatter and a basic structure. Example for `vpn.de.md`:

```markdown
---
title: VPN (WireGuard) einrichten
slug: vpn
icon: shield
version: 1.20.5
order: 2
---

# VPN (WireGuard) einrichten

WireGuard-VPN ermöglicht sicheren Fernzugriff auf dein BaluHost-NAS.

## Voraussetzungen

- Admin-Zugang zu BaluHost
- WireGuard muss auf dem Server installiert sein (`wg` Befehl verfügbar)
- Portweiterleitung am Router (Standard: UDP 51820)

## Schritte

1. Navigiere zu **Systemsteuerung → VPN**
2. Aktiviere den VPN-Server
3. Erstelle einen neuen Client
4. Scanne den QR-Code mit der WireGuard-App oder lade die Konfigurationsdatei herunter
```

Apply the same pattern for all 8 remaining topics (vpn, mobile, desktop-sync, pihole, smart-devices, notifications, samba, webdav) with appropriate `order` values (2-9), icons, and brief content.

- [ ] **Step 2: Create all English setup articles**

Same structure, translated to English.

- [ ] **Step 3: Commit**

```bash
git add client/src/content/manual/
git commit -m "feat(manual): add setup article placeholders for all 9 topics"
```

---

### Task 11: Add Tailwind typography plugin for prose styling

**Files:**
- Modify: `client/package.json`
- Modify: `client/tailwind.config.js` (or `tailwind.config.ts`)

The `ArticleView` component uses Tailwind's `prose` classes which require `@tailwindcss/typography`.

- [ ] **Step 1: Check if typography plugin is already installed**

```bash
cd client && grep -r "typography" tailwind.config.* package.json
```

If already present, skip this task entirely.

- [ ] **Step 2: Install plugin (only if not already present)**

```bash
cd client && npm install -D @tailwindcss/typography
```

- [ ] **Step 3: Add plugin to Tailwind config (only if not already present)**

In the Tailwind config file, add to the `plugins` array:

```javascript
plugins: [
  require('@tailwindcss/typography'),
  // ... existing plugins
],
```

- [ ] **Step 4: Verify build**

```bash
cd client && npm run build
```

Expected: Build succeeds.

- [ ] **Step 5: Commit (only if changes were made)**

```bash
git add client/package.json client/package-lock.json client/tailwind.config.*
git commit -m "chore: add @tailwindcss/typography for markdown rendering"
```

---

### Task 12: Manual smoke test

- [ ] **Step 1: Start dev server**

```bash
cd "D:/Programme (x86)/Baluhost" && python start_dev.py
```

- [ ] **Step 2: Verify navigation**

1. Open `http://localhost:5173`
2. Login with admin/DevMode2024
3. Sidebar should show "Benutzerhandbuch" (or "User Manual" in English) instead of "API-Center"
4. Click it — should navigate to `/manual`

- [ ] **Step 3: Verify tabs**

1. Setup tab (default) should show article cards (Cloud Import + all placeholders)
2. Wiki tab should show "Noch keine Artikel vorhanden" empty state
3. API Reference tab should show the full OpenAPI docs with category pills, search, endpoint cards

- [ ] **Step 4: Verify deep-links**

1. Navigate to `/manual?tab=setup&article=cloud-import` — should open the Cloud Import article directly
2. Click "Zurück zur Übersicht" — should return to the setup cards grid
3. Navigate to `/manual?tab=api` — should show API Reference

- [ ] **Step 5: Verify redirect**

1. Navigate to `/docs` — should redirect to `/manual`

- [ ] **Step 6: Verify version badges**

1. Global version badge in header shows current version (e.g. v1.20.5)
2. Article cards show version badges (green if current, amber if outdated)

- [ ] **Step 7: Verify language switching**

1. Switch language in settings to English
2. Return to User Manual — tab labels, article titles, and content should be in English
3. Switch back to German — everything in German
