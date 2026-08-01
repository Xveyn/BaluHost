# Notification-Abgleich für Clients

Gilt für Clients mit lokalem Bestand (BaluApp). Die Webapp braucht das nicht —
sie wird vom Server ausgeliefert und hat ohne ihn ohnehin keine Daten.

## Zeitstempel

| Feld | Bedeutung |
|---|---|
| `created_at` | Erstellung. Ändert sich nie. |
| `updated_at` | **Letzte Zustandsänderung.** Bewegt sich bei Lesen, Wegklicken, Wiederherstellen und Snooze — auch bei den Massenaktionen. |
| `deleted_at` | Zeitpunkt des Wegklickens, `null` = aktiv. |

Ein folgenloser Aufruf (etwa Wegklicken einer bereits weggeklickten Zeile)
schreibt nichts und bewegt `updated_at` deshalb **nicht**. Das ist Absicht:
sonst zöge jede Massenaktion den kompletten Bestand in jeden weiteren
inkrementellen Abruf.

## Inkrementell abfragen

`GET /api/notifications?updated_after=<ISO-8601>` und dasselbe auf
`/api/notifications/trash`. Der Client merkt sich das höchste gesehene
`updated_at` und schickt es beim nächsten Mal.

Paginierung: die Sortierung ist `created_at DESC`. Kommen während einer
Seitenfolge neue Notifications an, verschieben sich die Offsets. Wer sauber
durchblättern will, setzt zusätzlich `created_before` auf den Startzeitpunkt
des Durchlaufs.

## Konfliktauflösung

`is_read` ist **monoton** — es gibt keinen Endpunkt, der auf ungelesen
zurücksetzt. Zusammenführen per ODER: irgendwo gelesen ⇒ gelesen.

Für den Papierkorb-Zustand gilt Last-Write-Wins über `updated_at`.

## Endgültig gelöschte Zeilen (bewusste Entscheidung)

**Es gibt keine Grabsteine.** Hard-Deletes hinterlassen keine Spur, und das
bleibt so. Begründung:

1. **Der häufigste Fall ist vorhersagbar.** `cleanup_expired_trash()` löscht
   Papierkorb-Zeilen nach Ablauf der Retention — pro Nutzer 1–7 Tage aus
   `NotificationPreferences.trash_retention_days`, für System-Notifications
   fix 7 Tage. Eine Zeile, die der Client zuletzt mit `deleted_at = T` gesehen
   hat, ist nach `T + retention` weg. Der Client kann dieselbe Regel lokal
   anwenden; `trash_retention_days` liefert
   `GET /api/notifications/preferences`.
2. **Der Rest ist selten und nutzerinitiiert.** Übrig bleiben
   `DELETE /api/notifications/{id}` und `DELETE /api/notifications/trash` —
   bewusste Aktionen, typischerweise von einem verbundenen Gerät.

**Der Client muss deshalb periodisch einen Vollabgleich fahren**, um solche
Löschungen zu bemerken. Empfehlung: bei jedem Kaltstart, sonst täglich.

Diese Festlegung ersetzt Punkt 4 aus #504. Wird sie zu teuer — etwa weil der
Bestand pro Nutzer stark wächst — ist eine Grabstein-Tabelle die nächste
Ausbaustufe.
