import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl';
  /** Close when the user clicks the backdrop. Default: true. */
  closeOnOverlayClick?: boolean;
  /** Close when the user presses Escape. Default: true. */
  closeOnEscape?: boolean;
}

export function Modal({
  isOpen,
  onClose,
  title,
  children,
  size = 'md',
  closeOnOverlayClick = true,
  closeOnEscape = true,
}: ModalProps) {
  const sizeClasses = {
    sm: 'max-w-[95vw] sm:max-w-sm',
    md: 'max-w-[95vw] sm:max-w-md',
    lg: 'max-w-[95vw] sm:max-w-lg',
    xl: 'max-w-[95vw] sm:max-w-xl',
    '2xl': 'max-w-[95vw] sm:max-w-2xl lg:max-w-4xl',
  };

  // Close on Escape key
  useEffect(() => {
    if (!closeOnEscape) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose, closeOnEscape]);

  // Prevent body scroll when open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={closeOnOverlayClick ? onClose : undefined}
      />
      {/* Modal content */}
      <div
        className={`relative w-full ${sizeClasses[size]} max-h-[90vh] bg-slate-900 border border-slate-800/60 rounded-xl shadow-2xl flex flex-col`}
      >
        {/* Header */}
        {title && (
          <div className="flex items-center justify-between p-4 border-b border-slate-800/60 flex-shrink-0">
            <h3 className="text-lg font-semibold text-slate-100">
              {title}
            </h3>
            <button
              type="button"
              onClick={closeOnOverlayClick ? onClose : undefined}
              disabled={!closeOnOverlayClick}
              aria-label="Close"
              className={`p-1 rounded-lg transition-colors ${
                closeOnOverlayClick
                  ? 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                  : 'text-slate-700 cursor-not-allowed'
              }`}
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        )}
        {/* Body */}
        <div className="p-4 overflow-y-auto">{children}</div>
      </div>
    </div>,
    document.body
  );
}
