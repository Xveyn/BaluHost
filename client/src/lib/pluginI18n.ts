/**
 * Plugin i18n helper
 *
 * Resolves translated strings from plugin-provided translations.
 * Falls back through: current language → "en" → hardcoded fallback.
 */
import i18n from '../i18n';
import type { PluginTranslations } from '../api/plugins';

/**
 * Resolve a plugin string with i18n fallback.
 *
 * @param translations - Plugin translations dict (e.g. {"en": {"key": "val"}, "de": {...}})
 * @param key - Translation key to look up (e.g. "display_name")
 * @param fallback - Hardcoded fallback if no translation is found
 */
export function resolvePluginString(
  translations: PluginTranslations | undefined,
  key: string,
  fallback: string,
): string {
  if (!translations) return fallback;

  const lang = i18n.language?.split('-')[0]; // "de-DE" → "de"

  // Try current language
  if (lang && translations[lang]?.[key]) {
    return translations[lang][key];
  }

  // Try "en" fallback
  if (translations['en']?.[key]) {
    return translations['en'][key];
  }

  // Try first available language
  for (const langTranslations of Object.values(translations)) {
    if (langTranslations[key]) {
      return langTranslations[key];
    }
  }

  return fallback;
}
