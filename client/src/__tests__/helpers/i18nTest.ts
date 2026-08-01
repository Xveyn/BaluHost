/**
 * A real i18next instance for tests, loaded from the real locale files.
 *
 * Why not the app's `src/i18n`: that module is mocked globally in setup.ts
 * (formatters.ts imports it for locale detection), and it also installs a
 * language detector that reads the browser. A test needs a deterministic
 * language and the actual translations - so this builds its own instance from
 * the same JSON files.
 *
 * The namespaces are picked up with import.meta.glob rather than 22 import
 * lines: a new locale file is then covered automatically instead of silently
 * missing from every test.
 */
import i18n, { type i18n as I18nInstance } from 'i18next';
import { initReactI18next } from 'react-i18next';

type Bundle = Record<string, unknown>;

const localeModules = import.meta.glob<{ default: Bundle }>(
  '../../i18n/locales/*/*.json',
  { eager: true },
);

/** { de: { common: {...}, plugins: {...} }, en: {...} } */
function buildResources(): Record<string, Record<string, Bundle>> {
  const resources: Record<string, Record<string, Bundle>> = {};
  for (const [path, mod] of Object.entries(localeModules)) {
    const match = /\/locales\/([^/]+)\/([^/]+)\.json$/.exec(path);
    if (!match) continue;
    const [, language, namespace] = match;
    resources[language] ??= {};
    resources[language][namespace] = mod.default;
  }
  return resources;
}

export const testResources = buildResources();

export const availableNamespaces = Object.keys(testResources.de ?? {});

/**
 * A fresh instance per call — sharing one across tests would leak a language
 * switch from one test into the next.
 */
export function createTestI18n(language: 'de' | 'en' = 'de'): I18nInstance {
  const instance = i18n.createInstance();
  void instance.use(initReactI18next).init({
    lng: language,
    fallbackLng: 'de',
    ns: availableNamespaces,
    defaultNS: 'common',
    resources: testResources,
    interpolation: { escapeValue: false },
    // Tests assert on rendered output; suspending on a resource that is
    // already in memory would only add act() noise.
    react: { useSuspense: false },
    initImmediate: false,
  });
  return instance;
}
