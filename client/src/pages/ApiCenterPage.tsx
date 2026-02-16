import { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import {
  Code,
  Shield,
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
  Zap,
  Search,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { buildApiUrl } from '../lib/api';
import { apiSections, apiCategories, methodColors } from '../data/api-endpoints';
import type { ApiEndpoint } from '../data/api-endpoints';

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

// ==================== Rate Limit Mapping ====================

const rateLimitMap: Record<string, string> = {
  'POST /api/auth/login': 'auth_login',
  'POST /api/auth/register': 'auth_register',
  'GET /api/files/list': 'file_list',
  'POST /api/files/upload': 'file_upload',
  'GET /api/files/download/{path}': 'file_download',
  'DELETE /api/files/{path}': 'file_delete',
  'GET /api/shares': 'share_list',
  'POST /api/shares': 'share_create',
  'GET /api/system/info': 'system_monitor',
  'GET /api/system/telemetry': 'system_monitor',
  'POST /api/users': 'user_create',
};

// ==================== Endpoint Card Component ====================

interface EndpointCardProps {
  endpoint: ApiEndpoint;
  rateLimits: Record<string, RateLimitConfig>;
  t: (key: string) => string;
}

function EndpointCard({ endpoint, rateLimits, t }: EndpointCardProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const rateLimitKey = rateLimitMap[`${endpoint.method} ${endpoint.path}`];
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
        <div className="flex items-center gap-2 sm:gap-3 flex-1 flex-wrap min-w-0">
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
              <pre className="bg-slate-900/60 border border-slate-700/50 rounded-lg p-2 sm:p-3 text-[10px] sm:text-xs overflow-x-auto">
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
  const [user, setUser] = useState<User | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedSection, setSelectedSection] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [rateLimits, setRateLimits] = useState<Record<string, RateLimitConfig>>({});
  const [loading, setLoading] = useState(true);

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
      const token = localStorage.getItem('token');
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
      } catch (error) {
        console.error('Failed to fetch user:', error);
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
    const token = localStorage.getItem('token');
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
    } catch (error) {
      console.error('Failed to load rate limits:', error);
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
  }, [searchQuery, selectedCategory, selectedSection]);

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
            {t('system:apiCenter.subtitleFull')}
          </p>
        </div>
      </div>

      {/* Admin Rate Limits Link Card */}
      {isAdmin && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 sm:p-6">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-3">
              <Zap className="w-6 h-6 text-amber-400 flex-shrink-0" />
              <div>
                <h3 className="font-semibold text-white">{t('system:apiCenter.rateLimits.title')}</h3>
                <p className="text-sm text-slate-400">{t('system:apiCenter.rateLimits.movedDescription')}</p>
              </div>
            </div>
            <Link
              to="/admin/system-control?tab=ratelimits"
              className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-lg transition-colors text-sm font-medium touch-manipulation active:scale-95 whitespace-nowrap"
            >
              {t('system:apiCenter.rateLimits.goToSystemControl')} →
            </Link>
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
        <div className="space-y-2 sm:space-y-3">
          <div className="flex gap-1.5 sm:gap-2 flex-wrap">
            <button
              onClick={() => { setSelectedCategory(null); setSelectedSection(null); }}
              className={`px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium transition-all touch-manipulation active:scale-95 min-h-[36px] sm:min-h-0 whitespace-nowrap ${
                !selectedCategory
                  ? 'bg-cyan-600 text-white'
                  : 'bg-slate-800/40 text-slate-400 hover:bg-slate-700/50 hover:text-white'
              }`}
            >
              {t('system:apiCenter.all')}
              <span className="ml-1.5 text-[10px] opacity-70">({apiSections.reduce((sum, s) => sum + s.endpoints.length, 0)})</span>
            </button>
            {apiCategories.map((cat) => {
              const endpointCount = cat.sections.reduce((sum, s) => sum + s.endpoints.length, 0);
              return (
                <button
                  key={cat.id}
                  onClick={() => { setSelectedCategory(cat.id); setSelectedSection(null); }}
                  className={`px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium transition-all touch-manipulation active:scale-95 min-h-[36px] sm:min-h-0 whitespace-nowrap ${
                    selectedCategory === cat.id
                      ? 'bg-cyan-600 text-white'
                      : 'bg-slate-800/40 text-slate-400 hover:bg-slate-700/50 hover:text-white'
                  }`}
                >
                  {cat.label}
                  <span className="ml-1.5 text-[10px] opacity-70">({endpointCount})</span>
                </button>
              );
            })}
          </div>

          {/* Section Sub-Filter (only when a category is selected) */}
          {selectedCategory && currentCategorySections.length > 0 && (
            <div className="flex gap-1.5 sm:gap-2 flex-wrap pl-2 border-l-2 border-cyan-500/30">
              <button
                onClick={() => setSelectedSection(null)}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all touch-manipulation active:scale-95 min-h-[32px] whitespace-nowrap ${
                  !selectedSection
                    ? 'bg-violet-600 text-white'
                    : 'bg-slate-800/40 text-slate-400 hover:bg-slate-700/50 hover:text-white'
                }`}
              >
                {t('system:apiCenter.all')}
              </button>
              {currentCategorySections.map((section) => (
                <button
                  key={section.title}
                  onClick={() => setSelectedSection(section.title)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5 touch-manipulation active:scale-95 min-h-[32px] whitespace-nowrap ${
                    selectedSection === section.title
                      ? 'bg-violet-600 text-white'
                      : 'bg-slate-800/40 text-slate-400 hover:bg-slate-700/50 hover:text-white'
                  }`}
                >
                  {section.icon}
                  {section.title}
                  <span className="text-[10px] opacity-70">({section.endpoints.length})</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Loading State */}
      {loading && (
        <div className="text-slate-400 text-sm">{t('common:loading')}</div>
      )}

      {/* API Sections */}
      {!loading && visibleSections.map((section) => (
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
    </div>
  );
}
