#!/usr/bin/env python3
"""Exporta conversaciones desde la bandeja de entrada web de Kommo."""

import asyncio
from pathlib import Path

from playwright.async_api import Locator, Page, TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


URL_KOMMO = "https://tanakasaludablecali.kommo.com/chats/"
DIRECTORIO_SESION = Path("./kommo_session")
ARCHIVO_SALIDA = Path("conversaciones_kommo.txt")
SELECTOR_LISTA = ".chats-list, .chats-list-item"
SELECTOR_CHAT = ".chats-list-item"
SELECTOR_HISTORIAL = ".chat-history, .feed-compose"
SELECTOR_MENSAJE = ".chat-message, .feed-note"
SELECTORES_NOMBRE = (
    ".chat-header__title",
    ".feed-header__name",
    ".chats__conversation-name",
    ".chat-title",
)
ITERACIONES_SCROLL = 15
PAUSA_SCROLL_MS = 1_500


async def primer_visible(page: Page, selector: str) -> Locator:
    """Devuelve el primer elemento visible que coincide con ``selector``."""
    elementos = page.locator(selector)
    for indice in range(await elementos.count()):
        elemento = elementos.nth(indice)
        if await elemento.is_visible():
            return elemento
    raise RuntimeError(f"No se encontró un elemento visible para: {selector}")


async def nombre_chat(page: Page, elemento_lista: Locator, indice: int) -> str:
    """Lee el nombre del encabezado activo y usa la fila como alternativa."""
    for selector in SELECTORES_NOMBRE:
        candidatos = page.locator(selector)
        for posicion in range(await candidatos.count()):
            candidato = candidatos.nth(posicion)
            if await candidato.is_visible():
                texto = (await candidato.inner_text()).strip()
                if texto:
                    return texto.splitlines()[0].strip()

    texto_fila = (await elemento_lista.inner_text()).strip()
    return texto_fila.splitlines()[0].strip() if texto_fila else f"Chat {indice + 1}"


async def cargar_historial(historial: Locator) -> None:
    """Fuerza repetidamente el scroll superior para cargar mensajes antiguos."""
    for _ in range(ITERACIONES_SCROLL):
        await historial.evaluate("el => { el.scrollTop = 0; }")
        await historial.page.wait_for_timeout(PAUSA_SCROLL_MS)


async def extraer_mensajes(page: Page, historial: Locator) -> list[str]:
    """Extrae el texto visible de los nodos de mensajes del chat activo."""
    mensajes = historial.locator(SELECTOR_MENSAJE)
    if await mensajes.count() == 0:
        mensajes = page.locator(SELECTOR_MENSAJE)

    textos = []
    for indice in range(await mensajes.count()):
        mensaje = mensajes.nth(indice)
        if await mensaje.is_visible():
            texto = (await mensaje.inner_text()).strip()
            if texto:
                textos.append(texto)
    return textos


def formatear_chat(nombre: str, mensajes: list[str]) -> str:
    """Construye el bloque que se añade al archivo de salida."""
    lineas = ["=" * 40, f"CHAT: {nombre}", "=" * 40]
    lineas.extend(mensajes or ["[Sin mensajes visibles]"])
    return "\n".join(lineas) + "\n\n"


def guardar_chat(nombre: str, mensajes: list[str]) -> None:
    """Añade inmediatamente un chat al archivo para conservar el progreso."""
    with ARCHIVO_SALIDA.open("a", encoding="utf-8") as archivo:
        archivo.write(formatear_chat(nombre, mensajes))


async def exportar(page: Page) -> None:
    """Recorre ordenadamente las conversaciones actualmente cargadas."""
    try:
        await page.wait_for_selector(SELECTOR_LISTA, state="visible", timeout=120_000)
    except PlaywrightTimeoutError as error:
        raise RuntimeError(
            "No apareció la lista de chats en 120 segundos. "
            "Inicia sesión en Kommo y vuelve a ejecutar el script."
        ) from error

    cantidad = await page.locator(SELECTOR_CHAT).count()
    if cantidad == 0:
        raise RuntimeError("La bandeja está visible, pero no contiene chats abiertos.")

    ARCHIVO_SALIDA.write_text("", encoding="utf-8")
    print(f"Se encontraron {cantidad} chats. Iniciando exportación...")

    for indice in range(cantidad):
        try:
            # Se vuelve a crear el locator porque Kommo puede redibujar la lista.
            chat = page.locator(SELECTOR_CHAT).nth(indice)
            await chat.scroll_into_view_if_needed()
            await chat.click()
            await page.wait_for_timeout(1_000)

            historial = await primer_visible(page, SELECTOR_HISTORIAL)
            nombre = await nombre_chat(page, chat, indice)
            await cargar_historial(historial)
            mensajes = await extraer_mensajes(page, historial)
            guardar_chat(nombre, mensajes)
            print(f"[{indice + 1}/{cantidad}] Guardado: {nombre} ({len(mensajes)} mensajes)")
        except Exception as error:  # un chat defectuoso no detiene los demás
            print(f"[{indice + 1}/{cantidad}] Error al procesar el chat: {error}")


async def abrir_bandeja(page: Page) -> None:
    """Navega sin esperar a que toda la aplicación termine de cargar."""
    try:
        await page.goto(URL_KOMMO, wait_until="commit", timeout=120_000)
    except PlaywrightTimeoutError:
        # La lista de chats será la comprobación definitiva en ``exportar``.
        # Continuar permite que el usuario termine un inicio de sesión lento.
        print(
            "La navegación está tardando más de lo esperado; "
            "continuaré esperando la bandeja de Kommo..."
        )


async def main() -> None:
    """Abre una sesión persistente de Chromium y ejecuta la exportación."""
    DIRECTORIO_SESION.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        contexto = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(DIRECTORIO_SESION),
            headless=False,
            viewport={"width": 1440, "height": 900},
        )
        try:
            pagina = contexto.pages[0] if contexto.pages else await contexto.new_page()
            await abrir_bandeja(pagina)
            print("Esperando la bandeja. Si es la primera ejecución, inicia sesión manualmente.")
            await exportar(pagina)
            print(f"Exportación terminada: {ARCHIVO_SALIDA.resolve()}")
        finally:
            await contexto.close()


if __name__ == "__main__":
    asyncio.run(main())
