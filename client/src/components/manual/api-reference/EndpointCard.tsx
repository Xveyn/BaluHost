import { useState } from 'react';
import { ChevronDown, ChevronRight, Copy, Check, Zap, Shield } from 'lucide-react';
import { methodColors } from '../../../data/api-endpoints';
import type { ApiEndpoint } from '../../../data/api-endpoints';
import { matchEndpointToRateLimitType, type RateLimitConfig } from '../../../lib/apiRateLimitMatch';

export interface EndpointCardProps {
  endpoint: ApiEndpoint;
  rateLimits: Record<string, RateLimitConfig>;
  t: (key: string) => string;
}

export function EndpointCard({ endpoint, rateLimits, t }: EndpointCardProps) {
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
