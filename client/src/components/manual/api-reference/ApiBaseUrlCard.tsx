import { Code, Copy } from 'lucide-react';
import toast from 'react-hot-toast';

export interface ApiBaseUrlCardProps {
  apiBaseUrl: string;
  t: (key: string) => string;
}

export function ApiBaseUrlCard({ apiBaseUrl, t }: ApiBaseUrlCardProps) {
  return (
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
  );
}
