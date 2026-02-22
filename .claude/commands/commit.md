# Smart Commit: Änderungen in logische Commits aufteilen

Analysiere alle uncommitteten Änderungen und teile sie in logische, sinnvolle Commits auf.

## Workflow

### 1. Status erfassen

Führe parallel aus:
```bash
git status
git diff --stat
git diff --cached --stat
git log --oneline -10
```

Erfasse:
- Aktueller Branch
- Alle geänderten, neuen und gelöschten Dateien (staged + unstaged)
- Die letzten 10 Commits für den Commit-Message-Stil

### 2. Änderungen analysieren

Lies die Diffs aller geänderten Dateien:
```bash
git diff
git diff --cached
```

Für neue (untracked) Dateien: Lies den Inhalt der Dateien.

Gruppiere die Änderungen in **logische Commits** basierend auf:
- **Zusammengehörigkeit**: Dateien die zum gleichen Feature/Bugfix/Refactoring gehören
- **Conventional Commits**: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, `test:`, `perf:`, `style:`
- **Atomic Commits**: Jeder Commit sollte eine abgeschlossene, sinnvolle Einheit sein
- **Abhängigkeiten**: Wenn Commit B auf Commit A aufbaut, kommt A zuerst

### 3. Plan dem Benutzer zeigen

**ZEIGE DEM BENUTZER:**

```
Branch: <aktueller-branch>

Vorgeschlagene Commits:
━━━━━━━━━━━━━━━━━━━━━━

1. <commit-message>
   Dateien:
   - path/to/file1.py (modified)
   - path/to/file2.py (new)

2. <commit-message>
   Dateien:
   - path/to/file3.ts (modified)
   - path/to/file4.ts (deleted)

...
```

**FRAGE DEN BENUTZER:** Sollen diese Commits so erstellt werden? Der Benutzer kann:
- Bestätigen
- Commits zusammenlegen oder aufteilen
- Commit-Messages ändern
- Dateien zwischen Commits verschieben

### 4. Commits erstellen

Für jeden genehmigten Commit:

1. Nur die zugehörigen Dateien stagen:
   ```bash
   git add <datei1> <datei2> ...
   ```
   Für gelöschte Dateien: `git rm <datei>`

2. Commit erstellen:
   ```bash
   git commit -m "<message>"
   ```

3. Verifizieren dass der Commit erstellt wurde:
   ```bash
   git log --oneline -1
   ```

Wiederhole für alle Commits in der geplanten Reihenfolge.

### 5. Zusammenfassung

Zeige am Ende:
```
Erledigt! X Commits erstellt:

<git log --oneline der neuen commits>
```

## Regeln

- **NIEMALS** `git add -A` oder `git add .` verwenden — immer spezifische Dateien stagen
- **NIEMALS** `.env`, `.env.production`, Credentials oder Secrets committen — warnen falls vorhanden
- **NIEMALS** Commits ohne Bestätigung des Benutzers erstellen
- **KEINE** leeren Commits erstellen
- Commit-Messages auf Englisch (Conventional Commits Format)
- Commit-Messages sind kurz und beschreiben das "Warum", nicht das "Was"
- Bei Pre-Commit-Hook-Fehlern: Problem beheben und NEUEN Commit erstellen (nicht --amend)
- Jeder Commit endet mit: `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`
