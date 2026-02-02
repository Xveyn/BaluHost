import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

// Import locale files
import commonDe from './locales/de/common.json';
import commonEn from './locales/en/common.json';
import dashboardDe from './locales/de/dashboard.json';
import dashboardEn from './locales/en/dashboard.json';
import fileManagerDe from './locales/de/fileManager.json';
import fileManagerEn from './locales/en/fileManager.json';
import settingsDe from './locales/de/settings.json';
import settingsEn from './locales/en/settings.json';
import adminDe from './locales/de/admin.json';
import adminEn from './locales/en/admin.json';
import loginDe from './locales/de/login.json';
import loginEn from './locales/en/login.json';
import systemDe from './locales/de/system.json';
import systemEn from './locales/en/system.json';
import sharesDe from './locales/de/shares.json';
import sharesEn from './locales/en/shares.json';
import pluginsDe from './locales/de/plugins.json';
import pluginsEn from './locales/en/plugins.json';
import devicesDe from './locales/de/devices.json';
import devicesEn from './locales/en/devices.json';
import schedulerDe from './locales/de/scheduler.json';
import schedulerEn from './locales/en/scheduler.json';
import notificationsDe from './locales/de/notifications.json';
import notificationsEn from './locales/en/notifications.json';
import updatesDe from './locales/de/updates.json';
import updatesEn from './locales/en/updates.json';
import remoteServersDe from './locales/de/remoteServers.json';
import remoteServersEn from './locales/en/remoteServers.json';
import publicShareDe from './locales/de/publicShare.json';
import publicShareEn from './locales/en/publicShare.json';
import apiDocsDe from './locales/de/apiDocs.json';
import apiDocsEn from './locales/en/apiDocs.json';

const resources = {
  de: {
    common: commonDe,
    dashboard: dashboardDe,
    fileManager: fileManagerDe,
    settings: settingsDe,
    admin: adminDe,
    login: loginDe,
    system: systemDe,
    shares: sharesDe,
    plugins: pluginsDe,
    devices: devicesDe,
    scheduler: schedulerDe,
    notifications: notificationsDe,
    updates: updatesDe,
    remoteServers: remoteServersDe,
    publicShare: publicShareDe,
    apiDocs: apiDocsDe,
  },
  en: {
    common: commonEn,
    dashboard: dashboardEn,
    fileManager: fileManagerEn,
    settings: settingsEn,
    admin: adminEn,
    login: loginEn,
    system: systemEn,
    shares: sharesEn,
    plugins: pluginsEn,
    devices: devicesEn,
    scheduler: schedulerEn,
    notifications: notificationsEn,
    updates: updatesEn,
    remoteServers: remoteServersEn,
    publicShare: publicShareEn,
    apiDocs: apiDocsEn,
  },
};

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'de',
    defaultNS: 'common',
    ns: ['common', 'dashboard', 'fileManager', 'settings', 'admin', 'login', 'system', 'shares', 'plugins', 'devices', 'scheduler', 'notifications', 'updates', 'remoteServers', 'publicShare', 'apiDocs'],
    
    detection: {
      // Order of language detection methods
      order: ['localStorage', 'navigator', 'htmlTag'],
      // Cache user language preference in localStorage
      caches: ['localStorage'],
      // Key to use in localStorage
      lookupLocalStorage: 'baluhost-language',
    },
    
    interpolation: {
      escapeValue: false, // React already escapes values
    },
    
    react: {
      useSuspense: true,
    },
  });

export default i18n;

// Helper to get available languages
export const availableLanguages = [
  { code: 'de', name: 'Deutsch', flag: '🇩🇪' },
  { code: 'en', name: 'English', flag: '🇬🇧' },
];
