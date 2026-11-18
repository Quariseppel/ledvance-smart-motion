# LEDVANCE SMART+ Motion

Home-Assistant-Integration für LEDVANCE SMART+ WLAN-Bewegungsmelder, entwickelt für das Modell **AC61266023Y**. Sie liest Bewegungsstatus und den von SMART+ gemeldeten Akkustand aus der Cloud.

## Installation

1. Installiere den Konto-Client **HASS Ledvance**. Eine bestehende Installation des Ordners custom_components/hass_ledvance eignet sich dafür. [HASS Ledvance](https://github.com/buggedcom/hass-ledvance)
2. Öffne ab Home Assistant 2026.11 **Einstellungen → Marketplace → Über Link hinzufügen**. Füge dieses Repository hinzu und installiere es. In älteren kompatiblen Versionen füge den Link über **HACS → Benutzerdefinierte Repositories** als Integration hinzu.
3. Starte Home Assistant neu, falls es dazu auffordert.
4. Bei einer Neuinstallation öffne **Einstellungen → Geräte & Dienste → Integration hinzufügen → LEDVANCE SMART+ Motion**. Melde dich mit deinem LEDVANCE-SMART+-Konto an und wähle den Melder. Ein bereits eingerichteter Melder verwendet den vorhandenen Konfigurationseintrag.

[Marketplace in Home Assistant](https://www.home-assistant.io/integrations/marketplace/)

## Optionen

Öffne das Zahnrad am vorhandenen Integrationseintrag.

- **Abfrageintervall** – Bewegungsstatus alle 5 bis 300 Sekunden prüfen. Im Standardmodus sind 15 Sekunden eingestellt.
- **Zeitplan** – Immer abfragen, lokale Sonnenzeiten verwenden oder feste Uhrzeiten eingeben. Feste Zeitfenster können über Mitternacht reichen.
- **Rollläden** – Sind alle ausgewählten Rollläden geschlossen, kann die Abfrage auch außerhalb des Zeitfensters laufen. Der Modus „Nur bei geschlossenen Rollläden“ nutzt allein diesen Auslöser.
- **Akku** – Home Assistant prüft den gemeldeten Prozentwert alle 24 Stunden. Fällige Akkuabfragen in der Pause werden im nächsten aktiven Zeitraum nachgeholt. Einen einzelnen Wert von 0 % prüft die Integration nach zwei Minuten erneut. Die Entität zeigt auch den Zeitpunkt der letzten erfolgreichen Akkuabfrage.

Während der Pause starten keine Bewegungs- oder Akkuabfragen an SMART+. Die Bewegungsentität zeigt **Keine Bewegung** und das Attribut **Cloud-Abfrage aktiv** steht auf **Aus**. Die Erkennung in Home Assistant hängt von der Übertragung zur Cloud und vom gewählten Intervall ab. Kurze Bewegungssignale können zwischen zwei Abfragen liegen.

## Updates

Veröffentlichte Versionen erscheinen nach der Installation aus diesem Repository unter **Einstellungen → Updates**. Ein Neustart lädt die aktualisierten Integrationsdateien.
