# RAID Setup Wizard - Feature Dokumentation

## Übersicht
Der RAID Setup Wizard ist ein mehrstufiger Assistent zur Erstellung von RAID Arrays mit visueller Festplattenauswahl und intelligenter Validierung.

## Features

### Backend-Erweiterungen (`backend/app/services/raid.py`)

#### 1. Erweiterte Mock-Disks im Dev-Mode
- **7 simulierte Festplatten** mit unterschiedlichen Größen:
  - **RAID1 Pool 1:** `sda`, `sdb` (je 5 GB) - initial im RAID md0
  - **RAID1 Pool 2:** `sdc`, `sdd` (je 10 GB) - verfügbar
  - **RAID5 Pool:** `sde`, `sdf`, `sdg` (je 20 GB) - verfügbar
- **Gesamt-Hardware-Kapazität:** ~90 GB (physisch)
- Automatische Markierung ob Disk bereits in RAID verwendet wird

#### 2. Intelligente RAID-Validierung
- **RAID-Level spezifische Mindestanforderungen:**
  - RAID 0/1: Min. 2 Disks
  - RAID 5: Min. 3 Disks
  - RAID 6: Min. 4 Disks
  - RAID 10: Min. 4 Disks
- **Konflikt-Erkennung:** Verhindert Verwendung von Disks die bereits in Arrays sind
- **Kapazitätsberechnung:** Automatische Berechnung der nutzbaren Kapazität:
  - RAID 0: Summe aller Disks
  - RAID 1: Kleinste Disk
  - RAID 5: (n-1) × Disk-Größe
  - RAID 6: (n-2) × Disk-Größe
  - RAID 10: n/2 × Disk-Größe

### Frontend-Wizard (`client/src/components/RaidSetupWizard.tsx`)

#### 3-Schritt Setup-Prozess

##### Schritt 1: Festplatten auswählen
- **Visuelle Disk-Auswahl** mit Checkboxen
- Anzeige von:
  - Disk-Name (`/dev/sdX`)
  - Modell-Information
  - Kapazität
  - Partitions-Status
- **Filterung:** Nur freie (nicht im RAID) Disks auswählbar
- **Echtzeit-Feedback:** Anzahl ausgewählter Disks

##### Schritt 2: RAID-Level wählen
- **5 RAID-Level zur Auswahl:**
  - RAID 1 (empfohlen) - Spiegelung
  - RAID 0 - Striping
  - RAID 5 - Parity
  - RAID 6 - Double Parity
  - RAID 10 - Mirrored Stripe
- **Detaillierte Informationen** für jeden Level:
  - Beschreibung
  - Redundanz-Level
  - Kapazität
  - Performance-Charakteristik
- **Intelligente Filterung:** Nur RAID-Level die mit der Anzahl ausgewählter Disks möglich sind
- **Empfehlungs-Badge** für RAID 1

##### Schritt 3: Bestätigung
- **Anpassbarer Array-Name** (z.B. md1, md2)
- **Zusammenfassung:**
  - RAID-Level
  - Anzahl Festplatten
  - Verfügbare Kapazität (automatisch berechnet)
  - Liste ausgewählter Disks
- **Warnhinweis** über Datenverlust
- **Ein-Klick-Erstellung**

#### UI/UX Features
- **Fortschrittsanzeige** am oberen Rand
- **Navigation:** Vor/Zurück zwischen Schritten
- **Validierung:** Buttons nur aktiv wenn alle Anforderungen erfüllt
- **Dark Mode Design** konsistent mit Rest der App
- **Responsive Layout** für alle Bildschirmgrößen
- **Tooltips** bei deaktivierten Buttons

### Integration in RaidManagement

#### Verbesserte Button-Logik
- "Neues Array erstellen" Button:
  - Deaktiviert wenn < 2 freie Disks
  - Tooltip erklärt warum deaktiviert
  - Öffnet Wizard statt einfachem Formular

#### Automatische Aktualisierung
- Nach Array-Erstellung:
  - RAID-Status neu laden
  - Verfügbare Disks neu laden
  - Toast-Benachrichtigung

## Verwendung

### Im Dev-Mode
1. **Login:** `admin` / `admin`
2. **Navigation:** RAID Control Seite
3. **Click:** "Neues Array erstellen"
4. **Wizard durchlaufen:**
   - Disks auswählen (z.B. sdc, sdd)
   - RAID 1 wählen (empfohlen)
   - Array-Name vergeben (z.B. md1)
   - Erstellen bestätigen
5. **Ergebnis:** Neues Array erscheint in der Liste

### Beispiel-Szenarien

#### RAID 1 mit 2 Disks
- Disks: `sdc1`, `sdd1`
- Kapazität: 5 GB (gespiegelt)
- Redundanz: 1 Disk kann ausfallen

#### RAID 0 mit 4 Disks
- Disks: `sdc1`, `sdd1`, `sde1`, `sdf1`
- Kapazität: 20 GB (4 × 5 GB)
- Redundanz: Keine

#### RAID 5 mit 3 Disks
- Disks: `sdc1`, `sdd1`, `sde1`
- Kapazität: 10 GB (2 × 5 GB)
- Redundanz: 1 Disk kann ausfallen

## Technische Details

### API-Endpunkte
- `GET /api/system/raid/available-disks` - Liste verfügbarer Disks
- `POST /api/system/raid/create-array` - Array erstellen
  ```json
  {
    "name": "md1",
    "level": "raid1",
    "devices": ["sdc1", "sdd1"]
  }
  ```

### Validierungs-Logik
```typescript
// Frontend
const minDisks = {
  raid0: 2, raid1: 2,
  raid5: 3, raid6: 4, raid10: 4
};
const canProceed = selectedDisks.length >= minDisks[level];

// Backend
if len(devices) < min_devices:
    raise ValueError(f"{level} requires at least {min_devices} devices")
```

### Kapazitätsberechnung
```python
# Backend - raid.py
if level == "raid0":
    array_size = single_disk_size * device_count
elif level == "raid1":
    array_size = single_disk_size
elif level == "raid5":
    array_size = single_disk_size * (device_count - 1)
# ...
```

## Testing

### Manueller Test
1. Server starten: `python start_dev.py`
2. Browser öffnen: http://localhost:5173
3. Login als Admin
4. RAID Control → "Neues Array erstellen"
5. Wizard durchlaufen

### Test-Script
```bash
cd backend
.venv/Scripts/python scripts/test_raid_wizard.py
```

## Bekannte Einschränkungen

### Dev-Mode
- Festgelegte 6 Mock-Disks (keine dynamische Erweiterung)
- Alle Disks gleiche Größe (5 GB)
- Keine echte Formatierung/Partitionierung
- Simulierte RAID-Operationen

### Produktion (Linux mit mdadm)
- Benötigt `mdadm` installiert
- Root-Rechte für Array-Erstellung
- Echte Disk-Formatierung (Datenverlust!)

## Zukünftige Erweiterungen

### Mögliche Verbesserungen
- [ ] Hot-Spare Disks über Wizard hinzufügen
- [ ] Disk-Health-Status im Wizard anzeigen
- [ ] Array-Migration (RAID-Level ändern)
- [ ] Geschwindigkeits-Limits im Wizard konfigurieren
- [ ] Bitmap-Einstellungen im Wizard
- [ ] Array-Größe manuell anpassen (für ungleiche Disks)
- [ ] Vorschau der Performance-Charakteristik
- [ ] Empfehlungen basierend auf Use-Case (Storage/Speed/Balance)

## Dateien

### Neu erstellt
- `client/src/components/RaidSetupWizard.tsx` - Wizard-Komponente
- `backend/scripts/test_raid_wizard.py` - Test-Script
- `docs/RAID_SETUP_WIZARD.md` - Diese Dokumentation

### Modifiziert
- `backend/app/services/raid.py` - Mock-Disks + Validierung
- `client/src/pages/RaidManagement.tsx` - Wizard-Integration
