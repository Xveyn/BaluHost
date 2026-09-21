# Tray-Icons

Abgeleitet aus `client/src/assets/baluhost-logo.png` (256×256). Das dunkle
Hintergrundquadrat ist entfernt, sonst säße die Katze im Panel in einem Kasten.

**Nicht** `client/src-tauri/icons/icon.png`: Die Datei ist trotz ihrer
1024×1024 RGBA ein Tauri-Platzhalter — ein einfarbig blaues Quadrat ohne
jedes Motiv (genau eine Farbe im gesamten Bild). Zwei Reviews haben ihre
Abmessungen bestätigt; niemand hat sie angesehen. Wer das nicht weiß, greift
beim nächsten Mal wieder danach.

`client/public/baluhost-logo.svg` ist ebenfalls **nicht** die Quelle: 1,2 MB,
ein nachgezeichnetes Bitmap mit tausenden Pfadpunkten.

Zustände: `ok` (grüner Punkt unten rechts) · `warning` (gelber Punkt) ·
`critical` (roter Punkt) · `offline` (entsättigt, ohne Punkt).

Auch der ruhige Zustand trägt einen Punkt. Ohne Badge ließe sich „alles in
Ordnung" nicht von „Icon nicht geladen" oder „Zustand unbekannt"
unterscheiden. Bei `offline` trägt die Entsättigung die Aussage, dort wäre
ein Punkt irreführend — wir wissen ja gerade nichts. Der Zustand steckt im
Badge, nicht in der Färbung der Katze — eine rote Katze liest sich als
anderes Logo, nicht als Alarm.

Weil die Katze farbig bleibt, funktioniert sie auf hellen wie dunklen Panels;
es gibt bewusst keine Hell/Dunkel-Varianten.

Alle vier Größen werden gebraucht: `tray.py` legt sie per `QIcon.addFile()` in
*ein* Icon, damit Plasma auf HiDPI-Panels die passende wählt.
