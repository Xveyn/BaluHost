// UI Component Library for BaluHost
// These components are also exposed via window.BaluHost.ui for plugin use

export { Button } from './Button';
export type { ButtonProps } from './Button';

export { Card, CardHeader, CardContent, CardFooter } from './Card';
export type { CardProps, CardHeaderProps, CardContentProps, CardFooterProps } from './Card';

export { Badge } from './Badge';
export type { BadgeProps } from './Badge';

export { Modal } from './Modal';
export type { ModalProps } from './Modal';

export { Input, Textarea } from './Input';
export type { InputProps, TextareaProps } from './Input';

export { Select } from './Select';
export type { SelectProps, SelectOption } from './Select';

export { ProgressBar } from './ProgressBar';
export type { ProgressBarProps } from './ProgressBar';

export { Spinner, LoadingOverlay } from './Spinner';
export type { SpinnerProps, LoadingOverlayProps } from './Spinner';

export { EmptyState } from './EmptyState';
export type { EmptyStateProps } from './EmptyState';

export { Tabs, TabPanel } from './Tabs';
export type { TabsProps, TabPanelProps, Tab } from './Tabs';

export { ConfirmDialog } from './ConfirmDialog';
export type { ConfirmDialogProps } from './ConfirmDialog';

// Re-export AdminBadge for backwards compatibility
export { AdminBadge } from './AdminBadge';
