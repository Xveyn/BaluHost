# Internationalization (i18n)

Multi-language support via `i18next` + `react-i18next`. Currently supports German (de, default) and English (en).

## Setup (`index.ts`)

- `i18next` with `LanguageDetector` (checks `localStorage` key `baluhost-language`, falls back to browser language)
- `fallbackLng: 'de'` — German is the primary language
- `defaultNS: 'common'` — default namespace for `t()` calls
- `useSuspense: true` — components suspend until translations load

## Namespaces

Translations are split by feature domain. Each namespace is a separate JSON file in `locales/{lang}/`.

| Namespace | Scope |
|---|---|
| `common` | Shared strings (buttons, labels, errors, navigation) |
| `dashboard` | Dashboard page |
| `fileManager` | File manager page |
| `settings` | Settings page |
| `admin` | Admin panels |
| `login` | Login/register page |
| `system` | System monitor |
| `shares` | File sharing |
| `plugins` | Plugin management |
| `devices` | Device management |
| `scheduler` | Scheduler dashboard |
| `notifications` | Notification system |
| `updates` | Update page |
| `remoteServers` | Remote server profiles |
| `apiDocs` | API documentation page |
| `manual` | User manual |

## Usage in Components

```tsx
import { useTranslation } from 'react-i18next';

const MyComponent = () => {
  const { t } = useTranslation('fileManager');  // specify namespace
  return <h1>{t('title')}</h1>;
};
```

## Adding Translations

1. Add keys to both `locales/de/{namespace}.json` and `locales/en/{namespace}.json`
2. For a new namespace: create both JSON files, import in `index.ts`, add to `resources` and `ns` array
3. Always add both languages — missing keys fall back to German
