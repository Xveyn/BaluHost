"""Parser-Tests gegen die an der Produktionsmaschine gemessene pactl-Ausgabe."""
import json

from app.plugins.installed.audio_control.pactl import (
    parse_percent,
    parse_sinks,
    parse_streams,
    volume_percent,
)

# Wörtlich gemessen auf BaluNode (PipeWire 1.4.2), gekürzt um irrelevante Felder.
REAL_SINK_INPUT = {
    "index": 789,
    "driver": "PipeWire",
    "owner_module": None,
    "client": "788",
    "sink": 61,
    "corked": False,
    "mute": False,
    "volume": {
        "front-left": {"value": 36305, "value_percent": "55%", "db": "-15.39 dB"},
        "front-right": {"value": 36305, "value_percent": "55%", "db": "-15.39 dB"},
    },
    "balance": 0.00,
    "properties": {
        "client.api": "pipewire-pulse",
        "application.name": "Firefox",
        "application.process.id": "367248",
        "application.process.binary": "firefox-esr",
        "media.name": "(10) Caller Broke Into a Smoke Shop — YouTube",
        "media.class": "Stream/Output/Audio",
        "node.name": "Firefox",
    },
}

REAL_SINK = {
    "index": 61,
    "state": "SUSPENDED",
    "name": "alsa_output.pci-0000_0e_00.6.iec958-stereo",
    "description": "Ryzen HD Audio Controller Digitales Stereo (IEC958)",
    "driver": "PipeWire",
    "mute": False,
    "volume": {
        "front-left": {"value": 62259, "value_percent": "95%", "db": "-1.34 dB"},
        "front-right": {"value": 62259, "value_percent": "95%", "db": "-1.34 dB"},
    },
    "balance": 0.00,
    "base_volume": {"value": 65536, "value_percent": "100%", "db": "0.00 dB"},
    "active_port": "iec958-stereo-output",
    "properties": {"device.description": "Ryzen HD Audio Controller"},
}

REAL_SINK_GPU = {
    "index": 731,
    "state": "SUSPENDED",
    "name": "alsa_output.pci-0000_03_00.1.hdmi-stereo-extra3",
    "description": "Navi 31 HDMI/DP Audio Digital Stereo (HDMI 4)",
    "mute": False,
    "volume": {
        "front-left": {"value": 65536, "value_percent": "100%", "db": "0.00 dB"},
        "front-right": {"value": 65536, "value_percent": "100%", "db": "0.00 dB"},
    },
    "properties": {"device.description": "Navi 31 HDMI/DP Audio"},
}


class TestParsePercent:
    def test_strips_the_percent_sign(self):
        assert parse_percent("55%") == 55

    def test_accepts_a_plain_number(self):
        assert parse_percent(42) == 42

    def test_unparsable_input_becomes_zero(self):
        """Ein defekter Wert darf niemals eine Ausnahme nach oben werfen."""
        assert parse_percent("laut") == 0
        assert parse_percent(None) == 0
        assert parse_percent({}) == 0

    def test_negative_is_clamped_to_zero(self):
        assert parse_percent("-5%") == 0

    def test_infinite_string_becomes_zero(self):
        """float() akzeptiert 'inf%', erst int() faellt mit OverflowError um."""
        assert parse_percent("inf%") == 0
        assert parse_percent("-inf%") == 0

    def test_infinite_float_becomes_zero(self):
        """int(float('inf')) wirft OverflowError, keinen ValueError."""
        assert parse_percent(float("inf")) == 0

    def test_nan_float_becomes_zero(self):
        """int(float('nan')) wirft ValueError, aber ueber den Zahlen-Zweig."""
        assert parse_percent(float("nan")) == 0


class TestVolumePercent:
    def test_takes_the_maximum_across_channels(self):
        volume = {
            "front-left": {"value_percent": "40%"},
            "front-right": {"value_percent": "60%"},
        }
        assert volume_percent(volume) == 60

    def test_missing_volume_is_zero(self):
        assert volume_percent(None) == 0
        assert volume_percent({}) == 0


class TestParseStreams:
    def test_parses_the_measured_firefox_stream(self):
        streams = parse_streams([REAL_SINK_INPUT])
        assert len(streams) == 1
        stream = streams[0]
        assert stream.id == 789
        assert stream.sink_id == 61
        assert stream.application == "Firefox"
        assert stream.binary == "firefox-esr"
        assert stream.title == "(10) Caller Broke Into a Smoke Shop — YouTube"
        assert stream.volume_percent == 55
        assert stream.muted is False
        assert stream.corked is False

    def test_falls_back_to_node_name_then_placeholder(self):
        """Spiele über Proton fuellen application.name nicht zwingend."""
        without_app = json.loads(json.dumps(REAL_SINK_INPUT))
        del without_app["properties"]["application.name"]
        assert parse_streams([without_app])[0].application == "Firefox"

        without_both = json.loads(json.dumps(without_app))
        del without_both["properties"]["node.name"]
        assert parse_streams([without_both])[0].application == "Unbekannt"

    def test_filters_out_non_output_streams(self):
        recording = json.loads(json.dumps(REAL_SINK_INPUT))
        recording["properties"]["media.class"] = "Stream/Input/Audio"
        assert parse_streams([recording]) == []

    def test_empty_payload_is_an_empty_list(self):
        assert parse_streams([]) == []

    def test_garbage_entries_are_skipped_not_fatal(self):
        assert parse_streams([{"nonsense": True}, REAL_SINK_INPUT]) == parse_streams(
            [REAL_SINK_INPUT]
        )

    def test_an_infinite_channel_value_does_not_crash_the_whole_list(self):
        """Ein kaputter Kanalwert darf nicht die ganze Streamliste mitreissen."""
        broken = json.loads(json.dumps(REAL_SINK_INPUT))
        broken["volume"]["front-left"]["value_percent"] = "inf%"
        streams = parse_streams([broken])
        assert len(streams) == 1
        assert streams[0].volume_percent == 55


class TestParseSinks:
    def test_parses_a_sink_and_marks_the_default(self):
        sinks = parse_sinks([REAL_SINK], "alsa_output.pci-0000_0e_00.6.iec958-stereo")
        assert len(sinks) == 1
        sink = sinks[0]
        assert sink.id == 61
        assert sink.name == "alsa_output.pci-0000_0e_00.6.iec958-stereo"
        assert sink.description == "Ryzen HD Audio Controller Digitales Stereo (IEC958)"
        assert sink.volume_percent == 95
        assert sink.muted is False
        assert sink.is_default is True

    def test_an_absent_default_marks_nothing(self):
        """Das konfigurierte Bluetooth-Geraet fehlt meist — das ist zulaessig."""
        sinks = parse_sinks([REAL_SINK], "bluez_output.C8_2B_6B_35_0D_B3.1")
        assert sinks[0].is_default is False

    def test_no_default_name_marks_nothing(self):
        assert parse_sinks([REAL_SINK], None)[0].is_default is False

    def test_exactly_one_of_two_sinks_is_default(self):
        sinks = parse_sinks(
            [REAL_SINK, REAL_SINK_GPU], "alsa_output.pci-0000_0e_00.6.iec958-stereo"
        )
        assert [s.id for s in sinks] == [61, 731]
        assert [s.is_default for s in sinks] == [True, False]

    def test_a_sink_without_description_falls_back_to_its_name(self):
        bare = {k: v for k, v in REAL_SINK.items() if k != "description"}
        assert parse_sinks([bare], None)[0].description == bare["name"]

    def test_empty_payload_is_an_empty_list(self):
        assert parse_sinks([], None) == []

    def test_an_infinite_channel_value_does_not_crash_the_whole_list(self):
        """Ein kaputter Kanalwert darf nicht die ganze Geraeteliste mitreissen."""
        broken = json.loads(json.dumps(REAL_SINK))
        broken["volume"]["front-left"]["value_percent"] = "inf%"
        sinks = parse_sinks([broken], None)
        assert len(sinks) == 1
        assert sinks[0].volume_percent == 95
