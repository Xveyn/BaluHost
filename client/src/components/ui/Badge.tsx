import React from 'react';

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info';
  pulse?: boolean;
  className?: string;
}

export function Badge({ children, variant = 'default', pulse = false, className = '' }: BadgeProps) {
  const variantClasses = {
    default: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
    success: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-400',
    warning: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-400',
    danger: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-400',
    info: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-400',
  };

  const pulseColors = {
    default: 'bg-gray-500',
    success: 'bg-green-500',
    warning: 'bg-yellow-500',
    danger: 'bg-red-500',
    info: 'bg-blue-500',
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full ${variantClasses[variant]} ${className}`}
    >
      {pulse && (
        <span className={`w-2 h-2 rounded-full animate-pulse ${pulseColors[variant]}`} />
      )}
      {children}
    </span>
  );
}
