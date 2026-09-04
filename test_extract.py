import sys
import types
import unittest
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory


# Permite probar las funciones puras sin instalar los navegadores de Playwright.
if "playwright.async_api" not in sys.modules:
    async_api = types.ModuleType("playwright.async_api")
    async_api.Locator = object
    async_api.Page = object
    async_api.TimeoutError = TimeoutError
    async_api.async_playwright = object
    playwright = types.ModuleType("playwright")
    playwright.async_api = async_api
    sys.modules["playwright"] = playwright
    sys.modules["playwright.async_api"] = async_api

import extract


class ExtractTest(unittest.TestCase):
    def test_interpretar_fecha_acepta_iso_y_unix(self):
        self.assertEqual(extract.interpretar_fecha("2026-09-03T10:30:00Z"), date(2026, 9, 3))
        marca = str(datetime(2026, 9, 3, 12).timestamp())
        self.assertEqual(extract.interpretar_fecha(marca), date(2026, 9, 3))
        self.assertIsNone(extract.interpretar_fecha("sin fecha"))

    def test_formatear_chat_incluye_encabezado_y_mensajes(self):
        resultado = extract.formatear_chat("Ana", ["Hola", "¿Cómo estás?"])

        self.assertIn("=" * 40, resultado)
        self.assertIn("CHAT: Ana", resultado)
        self.assertIn("Hola\n¿Cómo estás?", resultado)

    def test_formatear_chat_indica_cuando_no_hay_mensajes(self):
        resultado = extract.formatear_chat("Chat vacío", [])

        self.assertIn("[Sin mensajes visibles]", resultado)

    def test_guardar_chat_anexa_resultados_progresivamente(self):
        salida_original = extract.ARCHIVO_SALIDA
        with TemporaryDirectory() as directorio:
            try:
                extract.ARCHIVO_SALIDA = Path(directorio) / "salida.txt"
                extract.guardar_chat("Ana", ["Uno"])
                extract.guardar_chat("Luis", ["Dos"])
                contenido = extract.ARCHIVO_SALIDA.read_text(encoding="utf-8")
            finally:
                extract.ARCHIVO_SALIDA = salida_original

        self.assertIn("CHAT: Ana", contenido)
        self.assertIn("CHAT: Luis", contenido)
        self.assertLess(contenido.index("CHAT: Ana"), contenido.index("CHAT: Luis"))


class AbrirBandejaTest(unittest.IsolatedAsyncioTestCase):
    async def test_conserva_mensajes_cuando_kommo_no_expone_la_fecha(self):
        class Vacio:
            async def count(self):
                return 0

        class Mensaje:
            async def is_visible(self):
                return True

            async def get_attribute(self, _atributo):
                return None

            def locator(self, _selector):
                return Vacio()

            async def inner_text(self):
                return "Hola, quiero información"

        class Mensajes:
            async def count(self):
                return 1

            def nth(self, _indice):
                return Mensaje()

        class Pagina:
            def locator(self, _selector):
                return Mensajes()

        textos, sin_fecha = await extract.extraer_mensajes(
            Pagina(), None, date(2026, 9, 1)
        )

        self.assertEqual(textos, ["Hola, quiero información"])
        self.assertEqual(sin_fecha, 1)

    async def test_desplaza_el_contenedor_de_la_lista(self):
        class Chat:
            async def evaluate(self, javascript):
                self.javascript = javascript
                return True

        chat = Chat()
        self.assertTrue(await extract.desplazar_lista_chats(chat))
        self.assertIn("scrollTop", chat.javascript)

    async def test_navega_sin_esperar_domcontentloaded(self):
        class Pagina:
            async def goto(self, url, **opciones):
                self.llamada = (url, opciones)

        pagina = Pagina()
        await extract.abrir_bandeja(pagina)

        self.assertEqual(pagina.llamada[0], extract.URL_KOMMO)
        self.assertEqual(pagina.llamada[1]["wait_until"], "commit")
        self.assertEqual(pagina.llamada[1]["timeout"], 120_000)

    async def test_timeout_no_impide_verificar_la_lista_despues(self):
        class Pagina:
            async def goto(self, *_args, **_opciones):
                raise extract.PlaywrightTimeoutError("lento")

        await extract.abrir_bandeja(Pagina())

    async def test_detecta_la_bandeja_visible(self):
        class Chat:
            async def is_visible(self):
                return True

        class Chats:
            async def count(self):
                return 1

            def nth(self, _indice):
                return Chat()

        class Pagina:
            def locator(self, selector):
                self.selector = selector
                return Chats()

        pagina = Pagina()
        await extract.esperar_inicio_sesion(pagina)

        self.assertEqual(pagina.selector, extract.SELECTOR_CHAT)

    async def test_usa_texto_de_lead_si_kommo_cambia_las_clases(self):
        class Vacio:
            async def count(self):
                return 0

        class Pagina:
            def locator(self, _selector):
                return Vacio()

            def get_by_text(self, patron):
                self.patron = patron
                return "chats por texto"

        pagina = Pagina()
        resultado = await extract.localizar_chats(pagina)

        self.assertEqual(resultado, "chats por texto")
        self.assertIsNotNone(pagina.patron.fullmatch("Lead #25166992"))

    async def test_informa_si_se_cierra_el_navegador_durante_la_espera(self):
        class Pagina:
            def locator(self, _selector):
                raise RuntimeError("driver cerrado")

        with self.assertRaisesRegex(RuntimeError, "No cierres la ventana"):
            await extract.esperar_inicio_sesion(Pagina())


if __name__ == "__main__":
    unittest.main()
