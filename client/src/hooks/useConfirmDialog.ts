import { useState, useCallback, type ReactNode } from 'react';
import { createElement } from 'react';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';

interface ConfirmOptions {
  title?: string;
  variant?: 'danger' | 'warning' | 'default';
  confirmLabel?: string;
  cancelLabel?: string;
}

interface UseConfirmDialogReturn {
  confirm: (message: string, options?: ConfirmOptions) => Promise<boolean>;
  dialog: ReactNode;
}

export function useConfirmDialog(): UseConfirmDialogReturn {
  const [state, setState] = useState<{
    open: boolean;
    message: string;
    options: ConfirmOptions;
    resolve: ((value: boolean) => void) | null;
  }>({
    open: false,
    message: '',
    options: {},
    resolve: null,
  });

  const confirm = useCallback((message: string, options: ConfirmOptions = {}): Promise<boolean> => {
    return new Promise((resolve) => {
      setState({ open: true, message, options, resolve });
    });
  }, []);

  const handleConfirm = useCallback(() => {
    state.resolve?.(true);
    setState((prev) => ({ ...prev, open: false, resolve: null }));
  }, [state.resolve]);

  const handleCancel = useCallback(() => {
    state.resolve?.(false);
    setState((prev) => ({ ...prev, open: false, resolve: null }));
  }, [state.resolve]);

  const dialog = createElement(ConfirmDialog, {
    open: state.open,
    message: state.message,
    title: state.options.title,
    variant: state.options.variant,
    confirmLabel: state.options.confirmLabel,
    cancelLabel: state.options.cancelLabel,
    onConfirm: handleConfirm,
    onCancel: handleCancel,
  });

  return { confirm, dialog };
}
