# VPN Auto-Connect & Home Network Detection - Implementation Plan

## Ziel
- **Heimnetz-Erkennung:** App erkennt, ob User im gleichen Netzwerk wie das NAS ist
- **VPN-Hinweis:** Banner/Dialog zeigt Hinweis zum VPN-Aktivieren wenn außerhalb
- **Auto-Import:** VPN-Config wird beim QR-Scan automatisch in Android registriert

## Architektur

### 1. Heimnetz-Erkennung
**Strategie:** Vergleiche Server-IP/Hostname mit aktuellem Netzwerk-Subnet

```kotlin
// NetworkStateManager.kt
fun isInHomeNetwork(serverUrl: String): Boolean {
    // Parse NAS IP from serverUrl (z.B. "http://192.168.178.21:8000")
    val nasIp = extractIpFromUrl(serverUrl)
    
    // Get device's current local IP
    val deviceIp = getCurrentLocalIp()
    
    // Compare subnet (first 3 octets for /24 networks)
    return isSameSubnet(nasIp, deviceIp)
}
```

**Alternativen:**
- SSID-Vergleich (WiFi SSID matchen) - **Nachteil:** Benötigt Location Permission
- Subnet-Check (IP-Adress-Vergleich) - **Empfohlen:** Keine Extra-Permissions

### 2. VPN Status Banner
**UI Component:**
```kotlin
@Composable
fun VpnStatusBanner(
    isInHomeNetwork: Boolean,
    hasVpnConfig: Boolean,
    onConnectVpn: () -> Unit
) {
    if (!isInHomeNetwork && hasVpnConfig) {
        // Show warning banner
    }
}
```

**Platzierung:**
- FilesScreen (Top)
- DashboardScreen (Top)
- SharesScreen (Top)

### 3. Auto-Import VPN Config
**Flow:**
1. QR-Code scannen → `ImportVpnConfigUseCase`
2. VPN-Config aus QR extrahieren (Base64)
3. **NEU:** Android VPN Tunnel automatisch registrieren
4. User um Erlaubnis fragen (VpnService.prepare())
5. Config in PreferencesManager speichern

**Implementierung:**
```kotlin
// ImportVpnConfigUseCase.kt
suspend fun importAndRegisterVpn(qrData: String): Result<VpnConfig> {
    val config = parseQrCode(qrData)
    
    // Save to preferences
    preferencesManager.saveVpnConfig(config)
    
    // Auto-register in Android VPN settings
    vpnTunnelManager.registerConfig(config)
    
    return Result.success(config)
}
```

## Implementierungs-Schritte

### Phase 1: Network State Detection (30 Min)
1. ✅ Erstelle `NetworkStateManager.kt`
   - `isInHomeNetwork(serverUrl)` Funktion
   - IP Subnet Vergleich
   - StateFlow für Reactive Updates
2. ✅ Erweitere `PreferencesManager`
   - `getServerUrl()` - Cached NAS Server URL
3. ✅ Integriere in ViewModels (DashboardViewModel, FilesViewModel)

### Phase 2: VPN Status Banner UI (20 Min)
1. ✅ Erstelle `VpnStatusBanner.kt` Composable
   - Warning-Design (Orange Banner)
   - "VPN aktivieren" Button
   - Dismissable (mit Snooze)
2. ✅ Integriere in Screens
   - FilesScreen
   - DashboardScreen

### Phase 3: Auto-Import VPN Config (40 Min)
1. ✅ Erweitere `ImportVpnConfigUseCase`
   - Auto-Register VPN Tunnel
2. ✅ Erstelle `VpnTunnelManager`
   - `registerConfig()` - Registriert Config in Android
   - Permission Handling
3. ✅ Update `RegisterDeviceScreen`
   - Auto-Import beim QR-Scan
   - Success-Feedback

### Phase 4: Optional - Auto-Connect (15 Min)
1. ⚠️ Auto-Connect VPN wenn außerhalb Heimnetz
   - User Preference Toggle
   - Background Service

## Permissions Needed

```xml
<!-- AndroidManifest.xml -->
<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" /> <!-- Already exists -->
<uses-permission android:name="android.permission.INTERNET" /> <!-- Already exists -->

<!-- Optional: Für SSID-Check (nicht empfohlen) -->
<!-- <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" /> -->
```

## Testing Checklist

- [ ] Heimnetz: App zeigt KEINE VPN-Warnung
- [ ] Mobiles Netz: App zeigt VPN-Warnung
- [ ] VPN aktivieren Button → Öffnet VpnScreen
- [ ] QR-Scan → VPN automatisch registriert
- [ ] VPN Permission Dialog erscheint
- [ ] Nach VPN-Aktivierung → Banner verschwindet

## Technische Details

### IP Subnet Check Algorithm
```kotlin
fun isSameSubnet(ip1: String, ip2: String, prefixLength: Int = 24): Boolean {
    val addr1 = InetAddress.getByName(ip1).address
    val addr2 = InetAddress.getByName(ip2).address
    
    val mask = -1 shl (32 - prefixLength)
    val subnet1 = ByteBuffer.wrap(addr1).int and mask
    val subnet2 = ByteBuffer.wrap(addr2).int and mask
    
    return subnet1 == subnet2
}
```

### VPN Auto-Register (WireGuard)
```kotlin
// Uses WireGuard Android API
val tunnel = Tunnel.create(configName, config)
tunnelManager.addTunnel(tunnel)
```

## Best Practices

1. **Network Check Caching:** Cache result für 30 Sekunden (avoid spam)
2. **User Preference:** Erlaube "Don't show again" Option
3. **Graceful Degradation:** App funktioniert auch ohne VPN
4. **Error Handling:** Falls VPN-Import fehlschlägt, zeige Fallback-Option
5. **Battery Optimization:** Network-Checks nur wenn App aktiv

---

**Status:** Ready for Implementation  
**Estimated Time:** ~2 Stunden  
**Priority:** High (UX-kritisch)
