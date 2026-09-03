import sys
import types
import unittest
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


if __name__ == "__main__":
    unittest.main()
