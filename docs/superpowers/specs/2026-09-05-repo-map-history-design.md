# Repo-Map: Zeitachse (Verlauf und Churn)

**Datum:** 2026-09-05
**Status:** Design abgenommen, Implementierungsplan ausstehend
**Baut auf:** PR #540 (`feat/repo-map-loc`) — die Basis-Scripts `scripts/repo_map*.py`
**Branch:** `feat/repo-map-history`

## Problem

`scripts/repo_map.py` liefert eine Momentaufnahme: LOC je Verzeichnis, Refactor-Score
je Datei, aktuell 2.685 Dateien und ~600.000 Zeilen mit 599 geflaggten Dateien.

Eine Momentaufnahme kann zwei Fragen prinzipiell nicht beantworten:

1. **Richtung.** "599 geflaggte Dateien" ist als Zahl unbrauchbar. Erst
   "612 → 599 über drei Monate" sagt, ob Aufräumen gegen den Zuwachs ankommt —
   also ob die 500-Zeilen-Konvention (#301) gewinnt oder verliert.
2. **Aktivität.** Der Report kennt Größe, aber nicht Änderungshäufigkeit. Eine
   große Datei, die niemand anfasst, ist fertig; eine mittelgroße mit hoher
   Änderungsrate ist der Schmerzpunkt.

## Messungen, die das Design tragen

Alle Zahlen an diesem Repo gemessen (3.107 Commits, Nov 2025 – Sep 2026):

| Messung | Ergebnis |
|---|---|
| Snapshot heute analysieren (2.685 Dateien) | 2,6 s |
| 40 Wochen-Snapshots: Pfad-Einträge | 60.443 |
| davon eindeutige Blobs | 6.844 (8,8× Dedup) |
| Alle 6.844 Blobs lesen (224 MB, `git cat-file --batch`) | 1,4 s |
| 11 Monats-Snapshots, reine Zeilenzählung | 0,9 s |

Git speichert unveränderte Dateien über Commits hinweg als denselben Blob. Wer pro
Blob-SHA cached, analysiert jede Dateiversion genau einmal. **Damit kostet die volle
Historie Sekunden, nicht Minuten** — und ein Persistenz-Layer, der Ergebnisse
zwischen Läufen aufhebt, wird überflüssig. Jeder Lauf rekonstruiert aus Git und
ist per Definition korrekt; nichts kann driften.

Belegter Nutzen aus einer Vorab-Messung (Code-Zeilen ohne i18n-Locales):

```
Monat      gesamt   Δ         backend/app  backend/tests  client/src
2026-02   181,905  +76,812         89,651        21,420      63,799
2026-04   242,375  +21,248        114,512        38,951      78,829
2026-06   289,588  +19,049        128,760        59,660      87,712
2026-08   321,703  +10,028        133,835        69,656     104,460
2026-09   322,211     +508        133,911        70,088     104,460
```

Zwei Aussagen, heute nicht ableitbar: Das Wachstum flacht scharf ab (+77k im
Februar auf +10k im August), und die Test-Ratio `backend/tests` gegen
`backend/app` steigt von 25 % auf 52 %.

## Nicht-Ziele

Die bestehende Score-Rangliste ist **gut** und wird nicht ersetzt. Eine Gegenprobe
gegen die Änderungshäufigkeit der letzten 6 Monate zeigte: von den Top-15 nach
Score ist nur 1 Eintrag unberührter Code. Churn verfeinert die Reihenfolge, es
repariert nichts. Die Hotspot-Tabelle tritt deshalb **neben** die Score-Rangliste,
nicht an ihre Stelle.

Ebenfalls nicht gebaut: Persistenz, Schwellwerte, Alarme, CI-Anbindung,
Autoren-Auswertung (Solo-Repo, ohne Aussage), interaktiver Zeit-Schieberegler.

LOC ist kein Qualitätsmaß. Der Verlauf ist ein Frage-Generator ("warum sind die
Services im Juni um 12k gewachsen?"), kein KPI.

## Architektur

### Content-Source

Der einzige Punkt, der Historie blockiert, ist `repo_map._read_text()`: es liest
von der Platte. Die Naht ist eine Content-Source:

```
ContentSource.read(path) -> str | None       # None bei binär/unlesbar
ContentSource.identity(path) -> str | None   # Blob-SHA; None im Worktree

WorktreeSource(root)          # heutiges Verhalten, unverändert
GitTreeSource(root, commit)   # ls-tree einmal, cat-file --batch gestreamt
```

`build_report()` nimmt eine Source statt eines Roots entgegen. Für den Normallauf
ändert sich nur die Konstruktion, nicht das Verhalten.

### Blob-Cache

`analyze_file` ist rein über `(path, text, thresholds)`. Cache-Key ist
`(blob_sha, path)` — der Pfad muss hinein, weil `is_generated()` und `kind`
pfadabhängig sind. Das ist der Hebel, der 60.443 Pfad-Einträge auf 6.844
Analysen reduziert.

Der Cache greift ausschließlich bei `GitTreeSource`. `WorktreeSource.identity()`
liefert `None` — im Normallauf gibt es nur einen Snapshot, also nichts zu
deduplizieren. Ein `None`-Identity umgeht den Cache, statt ihn zu vergiften.

### Snapshot-Wahl (Option A)

`git log --first-parent --format=%H %as`, je Periode der letzte Commit.
`--first-parent`, damit Snapshots den Zustand von `main` abbilden und nicht
zufällige Feature-Branch-Commits.

An jedem Snapshot läuft die **volle** Metrik, nicht nur die Zeilenzählung. Nur so
wird "geflaggte Dateien über die Zeit" beantwortbar — der Kernnutzen gegenüber #301.

### Churn (Option B)

Ein einziger `git log --numstat`-Durchlauf über denselben Zeitraum. Je Datei:
Commit-Anzahl, addierte und gelöschte Zeilen, zuletzt angefasst.

Zwei Fallen: `numstat` liefert bei Umbenennungen `{alt => neu}`-Syntax, die auf
den neuen Pfad gemappt werden muss, sonst zerfällt die Historie einer Datei in
zwei Hälften. Binärdateien liefern `-` statt Zahlen.

## CLI

| Flag | Default | Wirkung |
|---|---|---|
| `--history` | aus | schaltet Verlauf und Churn ein |
| `--interval monthly\|weekly` | `monthly` | Snapshot-Dichte (11 Punkte ≈ 2,5 s; 40 ≈ 9 s) |
| `--since YYYY-MM-DD` | Repo-Anfang | grenzt den Zeitraum ein |
| `--json PFAD` | — | schreibt die Verlaufsdaten roh heraus |

Historie ist **opt-in**: der tägliche "wo stehe ich"-Lauf bleibt bei 2,6 s.

`--json` ist das einzige Zugeständnis an spätere Automatisierung — eine Naht, an
der ein CI-Job oder ein Gate andocken kann, ohne dass heute Policy erfunden wird.

## Report

Eine HTML-Datei wie bisher, neue Sektion **Verlauf**, gezeichnet aus dem
eingebetteten JSON-Payload. Keine Chart-Library — die "keine Third-Party-Deps"-Regel
des Tools bleibt bestehen.

- LOC-Verlauf je Top-Level-Bereich (`backend/app`, `backend/tests`, `client/src`,
  `docs`, plus Sammelposten `sonstiges` — die Summe muss dem Gesamt-LOC entsprechen)
- Verlauf der geflaggten Dateien und der Score-Summe — die #301-Trendlinie
- Delta-Spalte im bestehenden Verzeichnisbaum: Wachstum seit dem vorherigen Snapshot
- Hotspot-Tabelle (Score × Commits) neben der bestehenden Score-Rangliste

## Module

Geschnitten, damit keine Datei die 500-Zeilen-Konvention reißt, die das Tool selbst
durchsetzt.

| Datei | Art | grob |
|---|---|---|
| `scripts/repo_map_history.py` | neu | Snapshot-Wahl, `GitTreeSource`, Churn, Serien | ~300 |
| `scripts/repo_map.py` | geändert | History-Flags, Source-Konstruktion | +60 |
| `scripts/repo_map_html.py` | geändert | Verlaufs-Sektion in Template und Payload | +60 |
| `scripts/test_repo_map_history.py` | neu | eigene Datei, sonst platzt die Grenze | ~250 |

## Tests

Neues Muster gegenüber der bestehenden Suite: echte Mini-Repos in `tmp_path`
(`git init` plus einige Commits) für Snapshot-Wahl, `GitTreeSource` und
Churn-Parsing inklusive Rename und Binärdatei. Serien-Aufbau und Payload bleiben
reine Funktionen und werden ohne Git getestet.

## Risiken

**`git cat-file --batch` verklemmt**, wenn erst alle SHAs geschrieben und dann
gelesen werden — der Pipe-Puffer läuft voll und der Prozess hängt. Beim Ausmessen
live aufgetreten (120 s Timeout). Braucht einen Feeder-Thread oder verschränktes
Lesen. Ausdrücklich hier notiert, damit es nicht erneut gebaut wird.

**Zu kurze Zeiträume** (`--since` von gestern, frisches Repo) ergeben null oder
einen Snapshot. Der Verlauf braucht mindestens zwei Punkte; darunter wird die
Sektion mit einem Hinweis ausgelassen statt mit einer leeren Achse gerendert.

**Alte Snapshots enthalten Pfade, die es heute nicht mehr gibt**, und Dateitypen,
die der Analyzer nicht kennt. `analyze_file` muss darauf so robust reagieren wie
heute auf Binärdateien: überspringen statt werfen. Ein Verlauf, der an einem
Streu-Blob aus dem Februar stirbt, ist wertlos.
