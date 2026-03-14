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
import { buildApiUrl } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import { methodColors } from '../data/api-endpoints';
import type { ApiEndpoint } from '../data/api-endpoints';
import { useOpenApiSchema } from '../hooks/useOpenApiSchema';
import { RateLimitsTab } from '../components/rate-limits';

// ==================== Types ====================

interface User {
  id: string;
  username: string;
  role: string;
}

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

/**
 * Dynamically match an API endpoint to its rate limit endpoint_type
 * based on HTTP method and path patterns (mirrors backend decorator usage).
 */
function matchEndpointToRateLimitType(method: string, path: string): string | null {
  const p = path.toLowerCase();
  const m = method.toUpperCase();

  // Auth endpoints (most specific first)
  if (m === 'POST' && p === '/api/auth/login') return 'auth_login';
  if (m === 'POST' && p === '/api/auth/register') return 'auth_register';
  if (m === 'POST' && p === '/api/auth/change-password') return 'auth_password_change';
  if (m === 'POST' && p === '/api/auth/refresh') return 'auth_refresh';
  if (m === 'POST' && p === '/api/auth/verify-2fa') return 'auth_2fa_verify';
  if (m === 'POST' && p.startsWith('/api/auth/2fa/')) return 'auth_2fa_setup';
  if (p.startsWith('/api/auth/')) return 'user_operations';

  // Files (specific before generic)
  if (p.startsWith('/api/files/upload/chunked')) return 'file_chunked';
  if (m === 'POST' && p.startsWith('/api/files/upload')) return 'file_upload';
  if (m === 'GET' && p.startsWith('/api/files/download')) return 'file_download';
  if (m === 'GET' && p.startsWith('/api/files/list')) return 'file_list';
  if (m === 'DELETE' && p.startsWith('/api/files/')) return 'file_delete';
  if (p.startsWith('/api/files/')) return 'file_write';

  // Activity
  if (p.startsWith('/api/activity/')) return 'file_list';

  // Shares
  if (['POST', 'PATCH', 'DELETE'].includes(m) && p.startsWith('/api/shares')) return 'share_create';
  if (p.startsWith('/api/shares')) return 'share_list';

  // Mobile
  if (m === 'POST' && (p === '/api/mobile/register' || p === '/api/mobile/token/generate')) return 'mobile_register';
  if (p.includes('/mobile/sync') || p.includes('/mobile/upload-queue')) return 'mobile_sync';

  // Desktop pairing
  if (p.includes('/desktop-pairing/device-code')) return 'desktop_pairing_request';
  if (p.includes('/desktop-pairing/token')) return 'desktop_pairing_poll';
  if (p.includes('/desktop-pairing/verify')) return 'desktop_pairing_verify';
  if (p.includes('/desktop-pairing/approve')) return 'desktop_pairing_approve';

  // VPN, Backup, Sync
  if (p.startsWith('/api/vpn/') || p === '/api/vpn') return 'vpn_operations';
  if (p.startsWith('/api/backup/') || p === '/api/backup') return 'backup_operations';
  if (p.startsWith('/api/sync/')) return 'sync_operations';

  // Benchmark (POST run before admin catch-all)
  if (m === 'POST' && p.includes('/benchmark/run')) return 'admin_benchmark';

  // API Keys
  if (p.startsWith('/api/api-keys')) return 'api_key_operations';

  // Users
  if (p.startsWith('/api/users')) return 'user_operations';

  // System / Monitoring / Energy (GET = monitor, else admin)
  if (p.startsWith('/api/system/') || p.startsWith('/api/monitoring/') || p.startsWith('/api/energy/')) {
    return m === 'GET' ? 'system_monitor' : 'admin_operations';
  }

  // VCL
  if (p.startsWith('/api/vcl/')) return m === 'GET' ? 'file_list' : 'file_write';

  // SSD Cache
  if (p.startsWith('/api/ssd-cache/')) return m === 'GET' ? 'file_list' : 'admin_operations';

  // Admin catch-all
  const adminPrefixes = [
    '/api/admin/', '/api/admin-db/', '/api/schedulers/', '/api/fans/',
    '/api/power/', '/api/pihole/', '/api/sleep/', '/api/cloud/',
    '/api/updates/', '/api/samba/', '/api/webdav/', '/api/plugins/',
    '/api/notifications/', '/api/benchmark/', '/api/tapo/',
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

export default function ApiCenterPage() {
  const { t } = useTranslation(['system', 'common']);
  const { token } = useAuth();
  const [user, setUser] = useState<User | null>(null);
  const [activeView, setActiveView] = useState<'docs' | 'limits'>('docs');
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedSection, setSelectedSection] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [rateLimits, setRateLimits] = useState<Record<string, RateLimitConfig>>({});
  const [loading, setLoading] = useState(true);

  const { sections: apiSections, categories: apiCategories, loading: schemaLoading, error: schemaError, refetch: refetchSchema } = useOpenApiSchema();

  const isAdmin = user?.role === 'admin';

  // Dynamically determine API base URL based on current location
  const getApiBaseUrl = (): string => {
    const hostname = window.location.hostname;
    const isDev = import.meta.env.DEV;

    // In development, backend runs on port 3001
    // In production, backend typically runs on port 8000
    const port = isDev ? 3001 : 8000;
    const protocol = window.location.protocol; // http: or https:

    return `${protocol}//${hostname}:${port}`;
  };

  const apiBaseUrl = getApiBaseUrl();

  // Load current user
  useEffect(() => {
    const fetchUser = async () => {
      if (!token) {
        setLoading(false);
        return;
      }

      try {
        const response = await fetch(buildApiUrl('/api/auth/me'), {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.ok) {
          const data = await response.json();
          setUser(data.user || data);
        }
      } catch {
        // User not authenticated
      }
    };
    fetchUser();
  }, []);

  // Load rate limits for displaying badges (admin only)
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
    <div className="space-y-4 sm:space-y-6 p-4 sm:p-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl lg:text-3xl font-bold bg-gradient-to-r from-cyan-400 via-blue-400 to-violet-400 bg-clip-text text-transparent flex items-center gap-2 sm:gap-3">
            <Code className="w-6 h-6 sm:w-8 sm:h-8 text-cyan-400" />
            {t('system:apiCenter.title')}
          </h1>
          <p className="text-slate-400 text-xs sm:text-sm mt-1">
            {isAdmin ? t('system:apiCenter.subtitleAdmin') : t('system:apiCenter.subtitleFull')}
          </p>
        </div>
        {activeView === 'docs' && (
          <button
            onClick={refetchSchema}
            className="p-2 bg-slate-800/40 hover:bg-slate-700/60 border border-slate-700/50 rounded-lg transition-colors touch-manipulation active:scale-95 self-start"
            title="Refresh API schema"
          >
            <RefreshCw className={`w-4 h-4 text-slate-400 ${schemaLoading ? 'animate-spin' : ''}`} />
          </button>
        )}
      </div>

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

      {/* ==================== Rate Limits View ==================== */}
      {activeView === 'limits' && isAdmin && <RateLimitsTab />}

      {/* ==================== API Docs View ==================== */}
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

      {/* Category Tabs */}
      {!searchQuery.trim() && (
        <div className="space-y-3">
          {/* Category Pills */}
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

          {/* Sub-Tabs (only for active category) */}
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
              {/* Fade gradient right - mobile only */}
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
