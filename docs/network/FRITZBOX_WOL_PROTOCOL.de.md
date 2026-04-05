# Fritz!Box TR-064 Wake-on-LAN-Protokoll

Dieses Dokument beschreibt, wie Wake-on-LAN über die TR-064-SOAP-API einer Fritz!Box gesendet wird.
Die BaluApp kann damit das NAS direkt aufwecken, wenn das NAS-Backend nicht erreichbar ist.

## Endpunkt

- **URL**: `http://<fritzbox-ip>:49000/upnp/control/hosts`
- **Methode**: POST
- **Auth**: HTTP Digest Authentication
- **Content-Type**: `text/xml; charset="utf-8"`

Port 49000 ist der Standard-TR-064-HTTP-Port. Einige Fritz!Box-Modelle unterstützen HTTPS auf Port 49443.

## SOAP Envelope

```xml
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:X_AVM-DE_WakeOnLANByMACAddress xmlns:u="urn:dslforum-org:service:Hosts:1">
      <NewMACAddress>AA:BB:CC:DD:EE:FF</NewMACAddress>
    </u:X_AVM-DE_WakeOnLANByMACAddress>
  </s:Body>
</s:Envelope>
```

## Erforderlicher Header

```
SOAPAction: "urn:dslforum-org:service:Hosts:1#X_AVM-DE_WakeOnLANByMACAddress"
```

## Authentifizierung

Die Fritz!Box verwendet HTTP Digest Authentication (RFC 7616).

- **Benutzername**: Oft leer bei der Fritz!Box (einfach `""`)
- **Passwort**: Das Fritz!Box-Admin-Passwort oder ein dediziertes TR-064-Benutzerpasswort
- Ein leerer Benutzername ist gültig und üblich -- die Auth-Bibliothek muss dies unterstützen

## Beispiel: cURL

```bash
curl -s --digest --user ":MyPassword" \
  -H 'Content-Type: text/xml; charset="utf-8"' \
  -H 'SOAPAction: "urn:dslforum-org:service:Hosts:1#X_AVM-DE_WakeOnLANByMACAddress"' \
  -d '<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:X_AVM-DE_WakeOnLANByMACAddress xmlns:u="urn:dslforum-org:service:Hosts:1">
      <NewMACAddress>AA:BB:CC:DD:EE:FF</NewMACAddress>
    </u:X_AVM-DE_WakeOnLANByMACAddress>
  </s:Body>
</s:Envelope>' \
  http://192.168.178.1:49000/upnp/control/hosts
```

Hinweis: `--user ":MyPassword"` -- der Doppelpunkt vor dem Passwort bedeutet leerer Benutzername.

## Beispiel: Kotlin (BaluApp)

```kotlin
import okhttp3.Credentials
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

suspend fun sendFritzBoxWol(
    host: String,
    port: Int = 49000,
    username: String = "",
    password: String,
    macAddress: String,
): Boolean {
    val url = "http://$host:$port/upnp/control/hosts"
    val soapBody = """
        <?xml version="1.0" encoding="utf-8"?>
        <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
                    s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
          <s:Body>
            <u:X_AVM-DE_WakeOnLANByMACAddress
              xmlns:u="urn:dslforum-org:service:Hosts:1">
              <NewMACAddress>$macAddress</NewMACAddress>
            </u:X_AVM-DE_WakeOnLANByMACAddress>
          </s:Body>
        </s:Envelope>
    """.trimIndent()

    // OkHttp verarbeitet Digest Auth über den Authenticator
    val client = OkHttpClient.Builder()
        .authenticator { _, response ->
            val credential = Credentials.basic(username, password)
            response.request.newBuilder()
                .header("Authorization", credential)
                .build()
        }
        .build()

    val request = Request.Builder()
        .url(url)
        .post(soapBody.toRequestBody("text/xml; charset=utf-8".toMediaType()))
        .header("SOAPAction",
            "\"urn:dslforum-org:service:Hosts:1#X_AVM-DE_WakeOnLANByMACAddress\"")
        .build()

    return withContext(Dispatchers.IO) {
        val response = client.newCall(request).execute()
        response.isSuccessful
    }
}
```

**Hinweis zur BaluApp-Implementierung**: Verwenden Sie OkHttps `DigestAuthenticator` oder eine dedizierte Digest-Auth-Bibliothek anstelle von Basic Auth -- das obige Beispiel ist vereinfacht. Die Fritz!Box erfordert Digest Auth.

## Speicherung der Zugangsdaten

Die BaluApp sollte:
1. Den Benutzer einmalig nach den Fritz!Box-Zugangsdaten fragen (Host, Port, Benutzername, Passwort)
2. Diese verschlüsselt lokal speichern (Android Keystore / EncryptedSharedPreferences)
3. Bei nachfolgenden WoL-Aufrufen wiederverwenden, ohne erneut nachzufragen
4. Dem Benutzer ermöglichen, die Zugangsdaten in den Einstellungen zu aktualisieren

## Verbindungstest

Um die Konnektivität zu prüfen, kann die Service-Beschreibung abgerufen werden:

```
GET http://<host>:<port>/hostsSCPD.xml
```

Eine 200-Antwort bestätigt, dass der TR-064-Dienst verfügbar ist. Ein 401 bedeutet, dass die Zugangsdaten falsch sind.

## Fehlerbehandlung

| HTTP-Code | Bedeutung |
|-----------|-----------|
| 200 | Erfolg (Body auf SOAP-Fault prüfen) |
| 401 | Authentifizierung fehlgeschlagen |
| Connection refused | Fritz!Box unter diesem Host:Port nicht erreichbar |
| Timeout | Fritz!Box antwortet nicht |

SOAP-Faults erscheinen innerhalb der 200-Antwort als `<s:Fault>`-Elemente. Parsen Sie den `<faultstring>` für die Fehlermeldung.
