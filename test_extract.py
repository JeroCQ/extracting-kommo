import sys
import types
import unittest


if "requests" not in sys.modules:
    requests_stub = types.ModuleType("requests")
    requests_stub.HTTPError = type("HTTPError", (Exception,), {})
    requests_stub.Session = object
    sys.modules["requests"] = requests_stub

import extract


class ExtractTest(unittest.TestCase):
    def test_referencia_mensaje_uses_event_pointer(self):
        event = {"value_after": [{"message": {"id": "abc", "talk_id": 42}}]}
        self.assertEqual(extract.referencia_mensaje(event), ("42", "abc"))

    def test_texto_mensaje_supports_text_and_attachment(self):
        self.assertEqual(extract.texto_mensaje({"text": " Hola "}), "Hola")
        self.assertEqual(
            extract.texto_mensaje({"attachment": {"type": "image"}}),
            "[Adjunto: image]",
        )

    def test_export_joins_event_to_talk_history(self):
        event = {
            "type": "incoming_chat_message",
            "entity_type": "lead",
            "entity_id": 7,
            "created_at": 100,
            "value_after": [{"message": {"id": "m1", "talk_id": 9}}],
        }
        original_events = extract.obtener_eventos
        original_history = extract.obtener_historial
        try:
            extract.obtener_eventos = lambda *_: [event]
            extract.obtener_historial = lambda *args: [{"id": "m1", "text": "Buenas"}]
            _, groups, errors = extract.exportar_conversaciones(object(), "url", 0)
        finally:
            extract.obtener_eventos = original_events
            extract.obtener_historial = original_history

        self.assertFalse(errors)
        self.assertIn("[Cliente]: Buenas", extract.formatear(groups))


if __name__ == "__main__":
    unittest.main()
