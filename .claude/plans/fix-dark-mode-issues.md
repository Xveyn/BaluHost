# Fix Dark Mode Issues

## Problem Summary
Nach dem Theme-Refactoring gibt es mehrere Probleme im Dark Mode:
1. 128 hardcoded `gray-*` Farben die nicht auf Themes reagieren
2. Kontrast-Probleme mit `text-muted` auf sekundären Hintergründen
3. Unvollständige Migration von `bg-interactive`

---

## Phase 1: Gray-Farben zu Theme-Variablen migrieren (128 Instanzen)

### 1.1 Text-Gray Migration
Mapping für Dark Mode Kompatibilität:

| Alte Klasse | Neue Klasse | Begründung |
|-------------|-------------|------------|
| `text-gray-700` | `text-theme-text-secondary` | Zu dunkel im Dark Mode → hellere Stufe |
| `text-gray-600` | `text-theme-text-secondary` | Zu dunkel → hellere Stufe |
| `text-gray-500` | `text-theme-text-tertiary` | Schlecht lesbar → tertiary |
| `text-gray-400` | `text-theme-text-tertiary` | Grenzwertig → tertiary |
| `text-gray-300` | `text-theme-text-secondary` | OK, aber konsistent machen |
| `text-gray-200` | `text-theme-text` | Primärtext |
| `text-gray-100` | `text-theme-text` | Primärtext |

### 1.2 Background-Gray Migration

| Alte Klasse | Neue Klasse |
|-------------|-------------|
| `bg-gray-900` | `bg-theme-bg` |
| `bg-gray-800` | `bg-theme-bg-secondary` |
| `bg-gray-700` | `bg-theme-bg-tertiary` |
| `bg-gray-600` | `bg-theme-bg-interactive` |
| `bg-gray-100/200` | `bg-theme-bg-secondary` |
| `bg-gray-50` | `bg-theme-bg` |

### 1.3 Border-Gray Migration

| Alte Klasse | Neue Klasse |
|-------------|-------------|
| `border-gray-700/600` | `border-theme-border` |
| `border-gray-300/200` | `border-theme-border-secondary` |

### Betroffene Dateien:
- [ ] `client/src/components/benchmark/BenchmarkPanel.tsx`
- [ ] `client/src/components/services/ServiceStatusCard.tsx`
- [ ] `client/src/components/services/ServiceCard.tsx`
- [ ] `client/src/components/EditShareLinkModal.tsx`
- [ ] `client/src/components/CreateFileShareModal.tsx`
- [ ] `client/src/components/CreateShareLinkModal.tsx`
- [ ] `client/src/components/RemoteServers/ServerProfileList.tsx`
- [ ] `client/src/components/RemoteServers/VPNProfileForm.tsx`
- [ ] `client/src/components/RemoteServers/ServerProfileForm.tsx`
- [ ] `client/src/components/RemoteServers/VPNProfileList.tsx`
- [ ] `client/src/components/EditFileShareModal.tsx`

---

## Phase 2: Kontrast-Verbesserung für `text-muted`

### Problem:
- `text-muted` (slate-500) auf `bg-secondary` (slate-800) = ~3.1:1 Kontrast
- WCAG AA erfordert 4.5:1

### Lösung A: `text-muted` aufhellen (empfohlen)
```tsx
// Aktuell:
'--color-text-muted': '100, 116, 139',  // slate-500

// Vorschlag - zwischen slate-400 und slate-500:
'--color-text-muted': '120, 140, 165',  // ~4.2:1 auf slate-800
```

### Lösung B: Selektive Verwendung
Alle `text-muted` auf nicht-primärem Hintergrund durch `text-tertiary` ersetzen.

### Aktion:
- [ ] Entscheidung treffen: Lösung A oder B
- [ ] Änderung implementieren
- [ ] Visuell testen

---

## Phase 3: `bg-interactive` Migration vervollständigen

### Fehlende Stellen (~17):
Suche nach:
- `bg-slate-600` ohne Theme-Variable
- Toggle-Track-Hintergründe
- Hover-States auf Buttons

```bash
grep -rn "bg-slate-600" client/src/ --include="*.tsx" | grep -v "theme"
```

### Aktion:
- [ ] Alle fehlenden Stellen identifizieren
- [ ] `bg-slate-600` → `bg-theme-bg-interactive` migrieren

---

## Phase 4: Verifikation

- [ ] Alle 6 Themes durchklicken und visuell prüfen
- [ ] Kontrast mit Browser DevTools prüfen
- [ ] Keine hardcoded `gray-*`, `slate-*` mehr (außer bewusste Ausnahmen)

---

## Priorisierung

1. **Kritisch**: Phase 1 (gray-Farben) - UI ist im Dark Mode teilweise unlesbar
2. **Hoch**: Phase 2 (Kontrast) - Accessibility-Problem
3. **Mittel**: Phase 3 (bg-interactive) - Inkonsistenz
4. **Niedrig**: Phase 4 (Verifikation) - QA

---

## Rollback
Falls Probleme auftreten:
```bash
git checkout HEAD -- client/src/
npm run build
```
