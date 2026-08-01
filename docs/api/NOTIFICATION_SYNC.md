# Notification-Abgleich für Clients

Gilt für Clients mit lokalem Bestand (BaluApp). Die Webapp braucht das nicht —
sie wird vom Server ausgeliefert und hat ohne ihn ohnehin keine Daten.

## Zeitstempel

| Feld | Bedeutung |
|---|---|
| `created_at` | Erstellung. Ändert sich nie. |
| `updated_at` | **Letzte Zustandsänderung.** Bewegt sich bei Lesen, Wegklicken und Wiederherstellen — auch bei den Massenaktionen. Snooze bewegt den Stempel ebenfalls, ist aber über `updated_after` nicht zuverlässig sichtbar — siehe eigener Abschnitt unten. |
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

## Snooze ist im Listenabgleich unsichtbar (bekannte Lücke)

Snooze bewegt `updated_at` wie jede andere Zustandsänderung — aber `GET
/api/notifications` und `GET /api/notifications/trash` filtern Zeilen mit
`snoozed_until > jetzt` aus beiden Listen heraus (aktiv **und** Papierkorb;
der Filter greift vor der Trash-Unterscheidung). Ergebnis: der Snooze-Aufruf
stempelt die Zeile und entfernt sie im selben Moment aus jeder Liste, in der
der Client sie hätte sehen können. Ein inkrementell abgleichender Client
bekommt vom Snooze nie ein Signal — die Zeile verschwindet einfach zwischen
zwei Abrufen, ununterscheidbar von einer harten Löschung.

Läuft der Snooze ab, taucht die Zeile serverseitig wieder in den Listen auf —
aber mit dem `updated_at`-Stempel vom Zeitpunkt des Snooze, der inzwischen
hinter dem Cursor liegen kann, den der Client zwischenzeitlich über andere
Zeilen erreicht hat. `updated_after` liefert die wiederaufgetauchte Zeile
dann nicht mehr. Ein Client, der ausschließlich inkrementell abgleicht, kann
eine anderswo gesnoozte und wieder aktive Notification unbegrenzt als
abwesend/erledigt behandeln.

Es gibt aktuell keinen serverseitigen Fix für diese Lücke (kein separates
Snooze-Ereignisfeld, kein Neustempeln beim Ablauf). Der periodische
Vollabgleich (siehe unten) fängt auch diesen Fall auf, weil er nicht auf
`updated_after` angewiesen ist.

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

Der Vollabgleich ist damit kein Nischenfall nur für harte Löschungen,
sondern der generelle Auffangmechanismus für alles, was `updated_after`
prinzipbedingt verpassen kann — das schließt die Snooze-Lücke oben ein und,
in Produktion, folgendes:

**`func.now()` ist die Transaktions-Startzeit, nicht die Commit-Zeit.** Unter
PostgreSQL — dem Produktivbetrieb mit vier Uvicorn-Workern — kann eine
Transaktion, die vor einer anderen gestartet, aber nach ihr committet wurde,
einen `updated_at`-Stempel schreiben, der bereits unter einem Cursor liegt,
den der Client zwischenzeitlich über die andere (früher committete)
Transaktion erreicht hat. Für den Client sieht das aus wie eine Zeile, die
`updated_after` grundlos übersprungen hat. Das ist kein Bug im Filter,
sondern eine inhärente Eigenschaft von `updated_after`-Abgleich unter
nebenläufigen Schreibern — der periodische Vollabgleich ist der Grund, warum
das folgenlos bleibt.

Diese Festlegung ersetzt Punkt 4 aus #504. Wird sie zu teuer — etwa weil der
Bestand pro Nutzer stark wächst — ist eine Grabstein-Tabelle die nächste
Ausbaustufe.
