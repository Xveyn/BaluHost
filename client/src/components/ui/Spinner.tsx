import { Loader2 } from 'lucide-react';

export interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg' | 'xl';
  className?: string;
  label?: string;
}

export function Spinner({ size = 'md', className = '', label }: SpinnerProps) {
  const sizeClasses = {
    sm: 'w-4 h-4',
    md: 'w-6 h-6',
    lg: 'w-8 h-8',
    xl: 'w-12 h-12',
  };

  return (
    <div className={`flex flex-col items-center justify-center gap-2 ${className}`}>
      <Loader2 className={`${sizeClasses[size]} animate-spin text-blue-500`} />
      {label && (
        <span className="text-sm text-gray-500 dark:text-gray-400">{label}</span>
      )}
    </div>
  );
}

export interface LoadingOverlayProps {
  label?: string;
}

export function LoadingOverlay({ label = 'Loading...' }: LoadingOverlayProps) {
  return (
    <div className="flex flex-col items-center justify-center h-64 gap-4">
      <div className="w-12 h-12 rounded-full bg-blue-100 dark:bg-blue-900/50 flex items-center justify-center">
        <Loader2 className="w-6 h-6 text-blue-600 dark:text-blue-400 animate-spin" />
      </div>
      <p className="text-gray-600 dark:text-gray-400">{label}</p>
    </div>
  );
}
