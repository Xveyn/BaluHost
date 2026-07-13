import { AlertTriangle } from 'lucide-react';

export interface ApiSchemaErrorProps {
  error: string;
  onRetry: () => void;
}

export function ApiSchemaError({ error, onRetry }: ApiSchemaErrorProps) {
  return (
    <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4">
      <div className="flex items-center gap-3">
        <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0" />
        <div className="flex-1">
          <p className="text-sm text-red-300">API schema could not be loaded: {error}</p>
        </div>
        <button
          onClick={onRetry}
          className="px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white rounded-lg transition-colors text-sm font-medium"
        >
          Retry
        </button>
      </div>
    </div>
  );
}
