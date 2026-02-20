# Release: development → main

Führe einen Release-Prozess durch, der development auf main merged und eine neue Version erstellt.

## Workflow

### 1. Status prüfen
- Prüfe ob wir auf dem `development` Branch sind
- Zeige alle Commits seit dem letzten Tag auf main
- Zeige eine Zusammenfassung der Änderungen

### 2. Versionsnummer bestimmen
**FRAGE DEN BENUTZER:** Welche Version soll erstellt werden?
- Zeige die aktuelle Version
- Schlage basierend auf den Änderungen vor:
  - PATCH (x.x.X) bei Bugfixes
  - MINOR (x.X.0) bei neuen Features
  - MAJOR (X.0.0) bei Breaking Changes

### 3. Version aktualisieren
Aktualisiere die Version in allen relevanten Dateien:
- `backend/pyproject.toml`
- `client/package.json`
- `CLAUDE.md`
- `client/src/data/api-endpoints/sections-features.ts` (API mock response)
- Dokumentationsdateien mit Versionsnummern

**FRAGE DEN BENUTZER:** Sollen diese Dateien aktualisiert werden? Zeige die Änderungen.

### 4. CHANGELOG aktualisieren
Erstelle einen CHANGELOG-Eintrag nach Keep a Changelog Format:
- Gruppiere nach: Added, Changed, Fixed, Removed
- Extrahiere Informationen aus den Commit-Messages
- Verwende Conventional Commits Präfixe (feat, fix, refactor, docs, chore)

**FRAGE DEN BENUTZER:** Ist der CHANGELOG-Eintrag korrekt? Zeige den Draft.

### 5. Commit erstellen
```bash
git add -A
git commit -m "chore: bump version to vX.X.X"
```

**FRAGE DEN BENUTZER:** Commit erstellen?

### 6. Auf main mergen
```bash
git checkout main
git merge development --ff-only
```

**FRAGE DEN BENUTZER:** Development auf main mergen?

### 7. Tag erstellen
```bash
git tag -a vX.X.X -m "Release vX.X.X - <kurze Beschreibung>"
```

**FRAGE DEN BENUTZER:** Tag erstellen?

### 8. Pushen
```bash
git push origin main
git push origin vX.X.X
```

**FRAGE DEN BENUTZER:** Änderungen und Tag pushen?

> **Hinweis:** Nach dem Push des Tags erstellt der GitHub Actions Workflow `.github/workflows/create-release.yml` automatisch ein GitHub Release mit den Release Notes aus dem CHANGELOG.

### 9. Zurück zu development
```bash
git checkout development
```

## Hinweise

- Bei Fehlern: Abbrechen und Status anzeigen
- Alle Befehle mit `--dry-run` simulieren wenn möglich
- Bei Konflikten: Benutzer informieren und manuell lösen lassen
- Excludierte Verzeichnisse in `.gitattributes` beachten
