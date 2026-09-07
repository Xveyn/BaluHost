# AMD GPU Power Management — sysfs-Berechtigungen

**Zielgruppe:** Admins, die GPU Power Management auf einer Maschine mit AMD-GPU aktivieren möchten und im UI **`WRITE PERMISSION: missing`** sehen.

**Symptom:** Im System Control → GPU Power Management steht oben rechts „missing", in den Logs erscheint:

```
AMD apply_state failed: [Errno 13] Permission denied:
'/sys/class/drm/card0/device/power_dpm_force_performance_level'
```

---

## Hintergrund

Der AMDGPU-Kerneltreiber legt zwei sysfs-Dateien an, die das Power Management von BaluHost beschreibt, um den GPU-Takt zwischen Active / Standby / Deep Idle zu wechseln:

| Datei | Zweck |
|---|---|
| `/sys/class/drm/card*/device/power_dpm_force_performance_level` | Erzwingt eine Power-Stufe (`auto`, `low`, `high`, `manual`) |
| `/sys/class/drm/card*/device/pp_power_profile_mode` | Wählt ein Profil (3D, Compute, VR, …) |

Dazu kommen (#516) vier weitere Dateien für die GPU-Lüfterakustik:

| Datei | Zweck |
|---|---|
| `/sys/class/drm/card*/device/gpu_od/fan_ctrl/fan_target_temperature` | Ziel-Temperatur der Lüfterkurve |
| `/sys/class/drm/card*/device/gpu_od/fan_ctrl/acoustic_limit_rpm_threshold` | Obere Lüfterdrehzahl-Grenze (Acoustic Limit) |
| `/sys/class/drm/card*/device/gpu_od/fan_ctrl/acoustic_target_rpm_threshold` | Ziel-Lüfterdrehzahl (Acoustic Target) |
| `/sys/class/drm/card*/device/gpu_od/fan_ctrl/fan_minimum_pwm` | Minimale PWM-Stufe des Lüfters |

**Wichtig:** `gpu_od/` entsteht erst, wenn der amdgpu-Treiber Overdrive für die
Karte initialisiert hat — auf Karten ohne (aktiviertes) Overdrive fehlt das
Verzeichnis schlicht. Die udev-Regel prüft deshalb vor jedem `chgrp`/`chmod`
mit `[ -e ]`, ob die Datei existiert, und überspringt sie sonst folgenlos.
Das bedeutet aber auch: ob die Regel für diese vier Dateien tatsächlich
greift, lässt sich nur nach einem echten Boot mit vorhandenem `gpu_od/`
verifizieren — und zwar an den Rechten selbst (`ls -la`), nicht daran, ob
die Akustik-Einstellung wirkt. Das Backend fällt bei `EACCES` auf
`sudo -n tee` zurück, und der vorhandene sudoers-Eintrag für
`/sys/class/hwmon/*` deckt den Schreibpfad ab — Wildcards
in sudoers-*Argumenten* matchen auch `/`, der Eintrag greift also bis in
`hwmonN/device/gpu_od/fan_ctrl/`. Die Werte greifen damit auch dann, wenn die
Knoten weiterhin `root:root 0644` tragen; die udev-Regel ist hier die
unprivilegierte Verbesserung, nicht die Voraussetzung.

**Diese Zusage gilt nur, solange der Primärzweig der Gerätepfad-Auflösung
greift.** `_device_from_hwmon()` (`backend/app/services/power/fan_gpu_manual.py`)
liefert dort `<hwmon>/device` unaufgelöst — der Pfad beginnt mit
`/sys/class/hwmon/` und fällt unter den Glob. Der Fallback-Zweig
(Aufwärtslauf über den aufgelösten Pfad) greift laut Docstring der Funktion
nur in synthetischen Bäumen: ein echtes `readlink -f` enthält auf realer
Hardware keine Komponente namens `device`. Schlägt der Primärzweig auf
abweichender Hardware fehl, liefert `_device_from_hwmon()` also `None`, und
`find_fan_ctrl_dir()` (`backend/app/services/power/fan_gpu_acoustics.py`, die
diese Funktion für die Akustik-Knoten wiederverwendet) findet gar kein
Verzeichnis. Die API meldet dann `available=false`, und das Akustik-Panel
bleibt schlicht aus — es kommt gar nicht erst zu einem Schreibversuch, also
auch zu keinem `EACCES`. Auf BaluNode läuft der an der Hardware verifizierte
Primärzweig; ob er auf abweichender AMD-Hardware ebenso zuverlässig greift,
ist unverifiziert. Weil ein Fehlschlagen dort als fehlende Schnittstelle
auftritt und nicht als Berechtigungsfehler, bleibt die udev-Regel dennoch die
konservative Absicherung: sie kostet nichts, solange `gpu_od/` existiert, und
deckt Fälle ab, die diese Analyse nicht vorhergesehen hat (#570).

Default-Permissions auf Debian 13 sind:

```
-rw-r--r-- 1 root root /sys/class/drm/card0/device/power_dpm_force_performance_level
-rw-r--r-- 1 root root /sys/class/drm/card0/device/pp_power_profile_mode
-rw-r--r-- 1 root root /sys/class/drm/card0/device/gpu_od/fan_ctrl/fan_target_temperature
-rw-r--r-- 1 root root /sys/class/drm/card0/device/gpu_od/fan_ctrl/acoustic_limit_rpm_threshold
-rw-r--r-- 1 root root /sys/class/drm/card0/device/gpu_od/fan_ctrl/acoustic_target_rpm_threshold
-rw-r--r-- 1 root root /sys/class/drm/card0/device/gpu_od/fan_ctrl/fan_minimum_pwm
```

→ Nur `root` kann schreiben. Der BaluHost-Backend-Service läuft aber als **`sven`** (oder dem bei der Installation gewählten User), nicht als root. Daraus folgt der `Permission denied`-Fehler.

## Lösung: udev-Regel + `video`-Gruppe

Das Vorgehen ist dasselbe Muster wie für `cpufreq`:

1. Eine udev-Regel ändert beim Boot (und bei jedem `add`/`change`-Event auf der DRM-Subsystem-Ebene) die Group-Ownership der sysfs-Dateien auf `video` und setzt das Group-Write-Bit.
2. Der BaluHost-Service-User wird in die `video`-Gruppe aufgenommen.
3. Service-Restart, damit die neue Gruppenmitgliedschaft greift.

**Bestandsserver mit #516 nachziehen:** Ein Server, auf dem die udev-Regel
schon vor #516 installiert wurde, trägt noch die alte, kürzere Dateiliste.
Die Regel muss einmal neu geschrieben werden, damit die vier Akustik-Knoten
dazukommen — entweder per Weg A (manuell) oder per Weg B mit
`SYNC_PERMISSIONS=1` (siehe unten). Ohne diesen einmaligen Re-Sync bleibt
`gpu_od/fan_ctrl/*` weiterhin `root:root 0644`, selbst wenn `gpu_od/` auf der
Maschine längst existiert.

## Anwenden in Production

Es gibt drei Wege:

### A) Einmalig manuell (schnellster Pfad für den aktuellen Server)

Auf dem Server, **als root**:

```bash
cd /opt/baluhost
sudo BALUHOST_USER=sven bash deploy/scripts/install-amd-gpu-permissions.sh
```

Sofortiger Effekt; restartet das Backend automatisch.

### B) Über den Auto-Deploy via GitHub Actions

Ab dem Branch mit der `SYNC_PERMISSIONS`-Variable:

1. **Einmalig** (auf dem Server, als root): die erweiterte Deploy-Sudoers-Datei
   übernehmen, damit der CI-Deploy ohne Passwort die udev-Rule installieren darf:

   ```bash
   cd /opt/baluhost
   git pull
   sudo BALUHOST_USER=sven bash deploy/scripts/install-deploy-sudoers.sh
   ```

   Danach ist `bash /opt/baluhost/deploy/scripts/install-amd-gpu-permissions.sh`
   für den Deploy-User in der Sudoers-Whitelist.

2. **Anschließend** in GitHub: Actions → "Deploy Production" → **Run workflow**
   → Häkchen bei *Re-apply OS-level permission grants* setzen → Run.

   Der CI-Deploy läuft normal durch (git pull, alembic upgrade, build, restart),
   ergänzt durch einen Schritt "OS Permission Grants (sync requested)", der
   das Standalone-Skript idempotent ausführt.

3. **Reguläre Push-Deploys** auf `main` ziehen die Permissions **nicht** neu
   (Variable Default = false). Datenbank-Verhalten bleibt unverändert.

### C) Frischinstallation auf neuem Host

Nichts zu tun. `deploy/install/modules/10-systemd-services.sh` deployed die
udev-Rule und fügt den User automatisch zur `video`-Gruppe hinzu.

Der Script:

1. Schreibt `/etc/udev/rules.d/70-baluhost-amd-gpu.rules`
2. Fügt `sven` (oder den durch `BALUHOST_USER` festgelegten User) zur `video`-Gruppe hinzu, falls noch nicht
3. Reloadet udev und triggert das DRM-Subsystem neu
4. Restartet `baluhost-backend.service`, damit der Prozess die neue Gruppenmitgliedschaft übernimmt

## Verifikation

**1. sysfs-Permissions:**

```bash
ls -la /sys/class/drm/card0/device/power_dpm_force_performance_level
# Erwartet: -rw-rw-r-- 1 root video
```

**1b. Akustik-Knoten (#516), nur falls `gpu_od/` existiert:**

```bash
ls -la /sys/class/drm/card0/device/gpu_od/fan_ctrl/
# Erwartet: alle vier Dateien -rw-rw-r-- 1 root video
```

Fehlt `gpu_od/` (noch) komplett, ist das kein Fehler der Regel — siehe
„Hintergrund" oben. Der verlässliche Test ist ein echter Reboot, nicht ein
manueller `udevadm trigger` direkt nach der Installation — und gemessen wird
mit diesem `ls -la`, nicht über die Funktion: dass sich Akustikwerte setzen
lassen, beweist wegen des `sudo -n tee`-Fallbacks nicht, dass die Regel
gegriffen hat.

**2. Backend-User in `video`-Gruppe:**

```bash
groups sven
# Erwartet: ... video ...
```

**3. UI / API:**

```bash
# In der UI: System Control → GPU Power Management → "WRITE PERMISSION: ok"
# Per API:
curl -s -H "Authorization: Bearer <admin-jwt>" \
  http://localhost:8000/api/gpu-power/status | jq '.has_write_permission'
# Erwartet: true
```

**4. Logs sauber:**

```bash
sudo journalctl -u baluhost-backend --since "5 minutes ago" | grep "AMD apply_state failed"
# Erwartet: keine Treffer
```

## Wenn du eine NVIDIA-GPU hast

Für NVIDIA wird `nvidia-smi` als Schreibinterface genutzt — das funktioniert ohne sysfs-Permission-Trick, weil `nvidia-smi` für nicht-root-User mit den richtigen Capabilities gebaut ist. Die hier beschriebene Regel ist AMD-spezifisch.

## Wenn neue AMD-GPUs / Hot-Plug

Die udev-Regel reagiert auf jedes `add|change`-Event im DRM-Subsystem. Eine neu eingesteckte AMD-Karte (Hot-Plug oder neuer PCIe-Slot nach Reboot) bekommt die korrekten Permissions automatisch — kein erneuter Skript-Lauf nötig.

## Zusammenhang mit anderen Berechtigungen

Diese Regel ist ein eigenständiger Fix für GPU Power Management. Sie ist **unabhängig** von:

- `polkit` für Logind-Sleep-Inhibitor (Datei `50-baluhost-inhibit-sleep.rules`)
- `cpufreq`-Gruppe für CPU Power Management
- Sudoers-Regeln für Update-Mechanismus

Wenn die UI bei mehreren Power-Karten "missing" zeigt, liegt für jede Stufe ein eigener Fix bei — siehe die jeweiligen Wiki-Einträge im Bereich Deployment.

## Related Files

- `deploy/install/templates/70-baluhost-amd-gpu.rules` — udev-Rule-Template
- `deploy/scripts/install-amd-gpu-permissions.sh` — Standalone-Setup-Skript
- `deploy/install/modules/10-systemd-services.sh` — Installer-Hook für Frischinstallationen
- `backend/app/services/power/gpu/amd_backend.py` — Code, der die sysfs-Files schreibt
