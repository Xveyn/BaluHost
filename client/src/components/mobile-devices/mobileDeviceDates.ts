import type { TFunction } from 'i18next';

export function formatMobileDate(dateString: string | null): string {
  if (!dateString) return 'Nie';
  const date = new Date(dateString);
  return date.toLocaleString('de-DE');
}

export interface MobileExpiry {
  daysLeft: number;
  isExpired: boolean;
  isExpiringSoon: boolean;
}

export function mobileExpiry(expiresAt: string): MobileExpiry {
  const expiresDate = new Date(expiresAt);
  const daysLeft = Math.ceil((expiresDate.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
  return { daysLeft, isExpired: daysLeft <= 0, isExpiringSoon: daysLeft <= 7 };
}

export function mobileTimeAgo(dateString: string | null, t: TFunction): string {
  if (!dateString) return t('time.never', 'Nie');
  const date = new Date(dateString);
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return t('time.justNow');
  if (seconds < 3600) return t('time.minutesAgo', { count: Math.floor(seconds / 60) });
  if (seconds < 86400) return t('time.hoursAgo', { count: Math.floor(seconds / 3600) });
  return t('time.daysAgo', { count: Math.floor(seconds / 86400) });
}

export function notificationTimeAgo(dateString: string): string {
  const sentDate = new Date(dateString);
  const seconds = Math.floor((Date.now() - sentDate.getTime()) / 1000);
  if (seconds < 60) return 'Gerade eben';
  if (seconds < 3600) return `Vor ${Math.floor(seconds / 60)} Min`;
  if (seconds < 86400) return `Vor ${Math.floor(seconds / 3600)} Std`;
  return `Vor ${Math.floor(seconds / 86400)} Tagen`;
}
