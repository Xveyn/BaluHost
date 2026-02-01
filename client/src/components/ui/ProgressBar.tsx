export interface ProgressBarProps {
  progress: number;
  variant?: 'default' | 'success' | 'warning' | 'danger';
  showLabel?: boolean;
  animated?: boolean;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

export function ProgressBar({
  progress,
  variant = 'default',
  showLabel = false,
  animated = true,
  className = '',
  size = 'md',
}: ProgressBarProps) {
  const variantClasses = {
    default: 'bg-gradient-to-r from-blue-500 to-blue-600',
    success: 'bg-gradient-to-r from-green-500 to-emerald-600',
    warning: 'bg-gradient-to-r from-yellow-500 to-orange-500',
    danger: 'bg-gradient-to-r from-red-500 to-rose-600',
  };

  const sizeClasses = {
    sm: 'h-1',
    md: 'h-2',
    lg: 'h-3',
  };

  const percent = Math.min(100, Math.max(0, progress));

  return (
    <div className={`relative ${className}`}>
      <div
        className={`w-full bg-gray-200 dark:bg-gray-700 rounded-full ${sizeClasses[size]} overflow-hidden`}
      >
        <div
          className={`h-full rounded-full transition-all duration-500 ${variantClasses[variant]} ${
            animated && percent < 100 ? 'animate-pulse' : ''
          }`}
          style={{ width: `${percent}%` }}
        />
      </div>
      {showLabel && (
        <span className="absolute right-0 -top-5 text-xs font-medium text-gray-600 dark:text-gray-400">
          {Math.round(percent)}%
        </span>
      )}
    </div>
  );
}
