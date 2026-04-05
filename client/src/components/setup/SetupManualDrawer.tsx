import { useState, useEffect, useCallback, useRef } from 'react';
import { X, BookOpen, ChevronRight, ArrowLeft, Loader2, GripVertical } from 'lucide-react';
import Markdown from 'react-markdown';
import { buildApiUrl } from '../../lib/api';

interface DocsArticleInfo {
  slug: string;
  title: string;
  icon: string;
}

interface DocsGroupInfo {
  id: string;
  label: string;
  icon: string;
  articles: DocsArticleInfo[];
}

interface SetupManualDrawerProps {
  open: boolean;
  onClose: () => void;
}

const MIN_WIDTH = 320;
const MAX_WIDTH_RATIO = 0.7; // max 70% of viewport
const DEFAULT_WIDTH = 480;

export function SetupManualDrawer({ open, onClose }: SetupManualDrawerProps) {
  const [groups, setGroups] = useState<DocsGroupInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null);
  const [selectedArticle, setSelectedArticle] = useState<string | null>(null);
  const [articleContent, setArticleContent] = useState<string>('');
  const [articleTitle, setArticleTitle] = useState<string>('');
  const [articleLoading, setArticleLoading] = useState(false);
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  const dragging = useRef(false);
  const startX = useRef(0);
  const startWidth = useRef(DEFAULT_WIDTH);

  // Drag resize
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;
    startX.current = e.clientX;
    startWidth.current = width;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [width]);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      const delta = startX.current - e.clientX;
      const maxWidth = window.innerWidth * MAX_WIDTH_RATIO;
      setWidth(Math.max(MIN_WIDTH, Math.min(maxWidth, startWidth.current + delta)));
    };

    const handleMouseUp = () => {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  // Load index on open
  useEffect(() => {
    if (!open) return;
    setLoading(true);
    fetch(buildApiUrl('/api/docs/index?lang=de'))
      .then((r) => r.json())
      .then((data) => setGroups(data.groups ?? []))
      .catch(() => setGroups([]))
      .finally(() => setLoading(false));
  }, [open]);

  // Load article
  useEffect(() => {
    if (!selectedArticle) return;
    setArticleLoading(true);
    fetch(buildApiUrl(`/api/docs/article/${selectedArticle}?lang=de`))
      .then((r) => r.json())
      .then((data) => {
        setArticleContent(data.content ?? '');
        setArticleTitle(data.title ?? '');
      })
      .catch(() => setArticleContent('Artikel konnte nicht geladen werden.'))
      .finally(() => setArticleLoading(false));
  }, [selectedArticle]);

  const handleBack = () => {
    if (selectedArticle) {
      setSelectedArticle(null);
      setArticleContent('');
    } else if (selectedGroup) {
      setSelectedGroup(null);
    }
  };

  const activeGroup = groups.find((g) => g.id === selectedGroup);

  if (!open) return null;

  return (
    <div
      className="fixed inset-y-0 right-0 z-50 flex flex-col bg-slate-900 border-l border-slate-800 shadow-2xl"
      style={{ width }}
    >
      {/* Drag handle */}
      <div
        onMouseDown={handleMouseDown}
        className="absolute inset-y-0 left-0 w-2 cursor-col-resize group z-10 flex items-center"
      >
        <div className="absolute inset-y-0 left-0 w-1 group-hover:bg-sky-500/40 transition-colors" />
        <div className="absolute left-0 top-1/2 -translate-y-1/2 rounded-r bg-slate-700/80 group-hover:bg-sky-500/60 transition-colors p-0.5">
          <GripVertical className="h-4 w-3 text-slate-500 group-hover:text-sky-300" />
        </div>
      </div>

      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
        <div className="flex items-center gap-3 min-w-0">
          {(selectedGroup || selectedArticle) && (
            <button
              onClick={handleBack}
              className="text-slate-400 hover:text-sky-400 transition-colors flex-shrink-0"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
          )}
          <BookOpen className="h-5 w-5 text-sky-400 flex-shrink-0" />
          <h2 className="text-lg font-semibold text-slate-100 truncate">
            {selectedArticle ? articleTitle : selectedGroup ? activeGroup?.label : 'Benutzerhandbuch'}
          </h2>
        </div>
        <button
          onClick={onClose}
          className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors flex-shrink-0"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-5 py-5">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-sky-400" />
          </div>
        ) : selectedArticle ? (
          articleLoading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="h-6 w-6 animate-spin text-sky-400" />
            </div>
          ) : (
            <article className="prose prose-invert prose-slate max-w-none prose-headings:text-white prose-h1:text-xl prose-h1:font-bold prose-h2:text-lg prose-h2:font-semibold prose-h2:mt-6 prose-h2:mb-3 prose-h3:text-base prose-h3:font-semibold prose-p:text-slate-300 prose-p:text-sm prose-p:leading-relaxed prose-li:text-slate-300 prose-li:text-sm prose-strong:text-white prose-code:text-sky-400 prose-code:bg-slate-900/60 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-pre:bg-slate-900/60 prose-pre:border prose-pre:border-slate-700/50 prose-pre:rounded-lg prose-a:text-sky-400 prose-a:no-underline hover:prose-a:underline">
              <Markdown>{articleContent}</Markdown>
            </article>
          )
        ) : selectedGroup && activeGroup ? (
          <div className="space-y-2">
            {activeGroup.articles.map((a) => (
              <button
                key={a.slug}
                onClick={() => setSelectedArticle(a.slug)}
                className="w-full flex items-center justify-between rounded-xl border border-slate-800/60 bg-slate-800/30 p-4 text-left hover:border-slate-700/80 transition-colors"
              >
                <span className="text-sm font-medium text-slate-200">{a.title}</span>
                <ChevronRight className="h-4 w-4 text-slate-500" />
              </button>
            ))}
          </div>
        ) : (
          <div className="space-y-2">
            {groups.map((group) => (
              <button
                key={group.id}
                onClick={() => setSelectedGroup(group.id)}
                className="w-full flex items-center justify-between rounded-xl border border-slate-800/60 bg-slate-800/30 p-4 text-left hover:border-slate-700/80 transition-colors"
              >
                <div>
                  <p className="text-sm font-medium text-slate-200">{group.label}</p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {group.articles.length} Artikel
                  </p>
                </div>
                <ChevronRight className="h-4 w-4 text-slate-500" />
              </button>
            ))}
            {groups.length === 0 && (
              <p className="text-sm text-slate-500 text-center py-8">
                Keine Dokumentation verfügbar.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
