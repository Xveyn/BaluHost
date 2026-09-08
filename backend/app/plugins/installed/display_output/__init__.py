"""Displaysteuerung — bundled Plugin.

Enumeriert die KWin-Ausgaenge und setzt Auswahl und Video-Modus ueber
kscreen-doctor. Laeuft als bundled Plugin im Host-Prozess und damit unter
derselben UID wie die Desktop-Session; ein Sandbox-Plugin kaeme nicht an den
Wayland-Socket.
"""
