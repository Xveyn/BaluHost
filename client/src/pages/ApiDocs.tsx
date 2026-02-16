import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Code,
  Lock,
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
  Shield
} from 'lucide-react';
import { apiSections, methodColors } from '../data/api-endpoints';
import type { ApiEndpoint } from '../data/api-endpoints';

function EndpointCard({ endpoint }: { endpoint: ApiEndpoint }) {
  const [isOpen, setIsOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="card mb-3 sm:mb-4">
      <div
        className="flex items-start sm:items-center justify-between cursor-pointer min-h-[44px] touch-manipulation"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="flex flex-col sm:flex-row sm:items-center gap-1.5 sm:gap-3 flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={`px-2 sm:px-3 py-1 rounded-lg text-[10px] sm:text-xs font-bold border ${methodColors[endpoint.method]}`}>
              {endpoint.method}
            </span>
            {endpoint.requiresAuth && (
              <span title="Requires authentication" className="sm:hidden"><Shield className="w-4 h-4 text-sky-400" /></span>
            )}
          </div>
          <code className="text-slate-300 font-mono text-xs sm:text-sm break-all">{endpoint.path}</code>
          <span className="text-slate-400 text-xs sm:text-sm hidden md:inline">{endpoint.description}</span>
          {endpoint.requiresAuth && (
            <span title="Requires authentication" className="hidden sm:inline"><Shield className="w-4 h-4 text-sky-400" /></span>
          )}
        </div>
        {isOpen ? (
          <ChevronDown className="w-5 h-5 text-slate-400 flex-shrink-0 ml-2" />
        ) : (
          <ChevronRight className="w-5 h-5 text-slate-400 flex-shrink-0 ml-2" />
        )}
      </div>

      {isOpen && (
        <div className="mt-4 space-y-4">
          {endpoint.params && endpoint.params.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-slate-300 mb-2">Parameters</h4>
              <div className="space-y-2">
                {endpoint.params.map((param, idx) => (
                  <div key={idx} className="flex items-start gap-3 text-sm">
                    <code className="text-sky-400 font-mono">{param.name}</code>
                    <span className="text-slate-500">({param.type})</span>
                    {param.required && (
                      <span className="text-red-400 text-xs">required</span>
                    )}
                    <span className="text-slate-400">{param.description}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {endpoint.body && endpoint.body.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-slate-300 mb-2">Request Body</h4>
              <div className="space-y-2">
                {endpoint.body.map((field, idx) => (
                  <div key={idx} className="flex items-start gap-3 text-sm">
                    <code className="text-violet-400 font-mono">{field.field}</code>
                    <span className="text-slate-500">({field.type})</span>
                    {field.required && (
                      <span className="text-red-400 text-xs">required</span>
                    )}
                    <span className="text-slate-400">{field.description}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {endpoint.response && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-semibold text-slate-300">Response Example</h4>
                <button
                  onClick={() => copyToClipboard(endpoint.response!)}
                  className="text-slate-400 hover:text-sky-400 transition-colors p-1"
                >
                  {copied ? (
                    <Check className="w-4 h-4 text-green-400" />
                  ) : (
                    <Copy className="w-4 h-4" />
                  )}
                </button>
              </div>
              <pre className="bg-slate-950/60 border border-slate-800 rounded-lg p-4 text-xs overflow-x-auto">
                <code className="text-slate-300">{endpoint.response}</code>
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ApiDocs() {
  const { t } = useTranslation(['apiDocs', 'common']);
  const [selectedSection, setSelectedSection] = useState<string | null>(null);
  const [showAuth, setShowAuth] = useState(false);
  const [tokenInput, setTokenInput] = useState('');
  const [authorized, setAuthorized] = useState(false);

  useEffect(() => {
    const t = localStorage.getItem('token');
    if (t) {
      setAuthorized(true);
      setTokenInput(t);
    }
  }, []);

  const openAuth = () => setShowAuth(true);
  const closeAuth = () => setShowAuth(false);
  const saveAuth = () => {
    const v = tokenInput.trim();
    if (!v) return;
    localStorage.setItem('token', v);
    setAuthorized(true);
    setShowAuth(false);
  };

  const clearAuth = () => {
    localStorage.removeItem('token');
    setAuthorized(false);
    setTokenInput('');
    setShowAuth(false);
  };

  const filteredSections = selectedSection
    ? apiSections.filter(s => s.title === selectedSection)
    : apiSections;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold bg-gradient-to-r from-sky-400 via-indigo-400 to-violet-400 bg-clip-text text-transparent">
            {t('title')}
          </h1>
          <p className="text-slate-400 mt-1 sm:mt-2 text-xs sm:text-sm">
            {t('subtitle')}
          </p>
        </div>
        <>
          <button className="btn btn-primary min-h-[44px] touch-manipulation active:scale-95 transition-transform" onClick={openAuth}>
            {authorized ? (
              <Check className="w-4 h-4 text-green-300" />
            ) : (
              <Lock className="w-4 h-4" />
            )}
            <span className="ml-2">{authorized ? t('authorize.authorized') : t('authorize.button')}</span>
          </button>

          {showAuth && (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4">
              <div className="absolute inset-0 bg-black/60" onClick={closeAuth} />
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 sm:p-6 w-full max-w-lg z-10 max-h-[90vh] overflow-y-auto">
                <h3 className="text-base sm:text-lg font-semibold text-slate-100 mb-3">{t('authorize.title')}</h3>
                <p className="text-xs sm:text-sm text-slate-400 mb-3">{t('authorize.description')}</p>
                <input
                  value={tokenInput}
                  onChange={(e) => setTokenInput(e.target.value)}
                  placeholder={t('authorize.placeholder')}
                  className="w-full bg-slate-950/60 border border-slate-800 rounded px-3 py-2.5 text-sm text-slate-200 mb-4 min-h-[44px]"
                />
                <div className="flex flex-col-reverse sm:flex-row gap-2 sm:justify-end">
                  <button className="btn btn-secondary min-h-[44px] touch-manipulation active:scale-95 transition-transform" onClick={clearAuth}>{t('authorize.clear')}</button>
                  <button className="btn min-h-[44px] touch-manipulation active:scale-95 transition-transform" onClick={closeAuth}>{t('authorize.cancel')}</button>
                  <button className="btn btn-primary min-h-[44px] touch-manipulation active:scale-95 transition-transform" onClick={saveAuth}>{t('authorize.save')}</button>
                </div>
              </div>
            </div>
          )}
        </>
      </div>

      {/* Info Card */}
      <div className="glass-accent border-l-4 border-l-sky-500">
        <div className="flex items-start gap-3">
          <Code className="w-5 h-5 text-sky-400 mt-0.5" />
          <div>
            <h3 className="font-semibold text-slate-200 mb-1">{t('baseUrl.title')}</h3>
            <code className="text-sm text-sky-400 bg-slate-950/60 px-3 py-1 rounded">
              http://localhost:8000
            </code>
            <p className="text-sm text-slate-400 mt-2">
              {t('baseUrl.authInfo')}
            </p>
            <code className="text-xs text-slate-300 bg-slate-950/60 px-3 py-1 rounded mt-2 inline-block">
              Authorization: Bearer {"<"}access_token{">"}
            </code>
          </div>
        </div>
      </div>

      {/* Section Filter */}
      <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0 pb-2">
        <div className="flex gap-2 min-w-max sm:flex-wrap sm:min-w-0">
          <button
            onClick={() => setSelectedSection(null)}
            className={`btn min-h-[44px] whitespace-nowrap touch-manipulation active:scale-95 transition-transform ${!selectedSection ? 'btn-primary' : 'btn-secondary'}`}
          >
            {t('filters.allEndpoints')}
          </button>
          {apiSections.map((section) => (
            <button
              key={section.title}
              onClick={() => setSelectedSection(section.title)}
              className={`btn min-h-[44px] whitespace-nowrap touch-manipulation active:scale-95 transition-transform ${selectedSection === section.title ? 'btn-primary' : 'btn-secondary'}`}
            >
              {section.icon}
              <span className="hidden sm:inline ml-1">{section.title}</span>
            </button>
          ))}
        </div>
      </div>

      {/* API Sections */}
      {filteredSections.map((section) => (
        <div key={section.title}>
          <div className="flex items-center gap-2 sm:gap-3 mb-3 sm:mb-4">
            <div className="glow-ring p-1.5 sm:p-2">
              {section.icon}
            </div>
            <h2 className="text-xl sm:text-2xl font-bold text-slate-100">{section.title}</h2>
            <span className="text-xs text-slate-500 ml-2">({section.endpoints.length})</span>
          </div>
          <div className="space-y-2 sm:space-y-3">
            {section.endpoints.map((endpoint, idx) => (
              <EndpointCard key={idx} endpoint={endpoint} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
