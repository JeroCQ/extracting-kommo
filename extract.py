#!/usr/bin/env python3
"""Exporta conversaciones desde la bandeja de entrada web de Kommo."""

import asyncio
import argparse
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import Locator, Page, TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


URL_KOMMO = "https://tanakasaludablecali.kommo.com/chats/"
DIRECTORIO_SESION = Path("./kommo_session")
ARCHIVO_SALIDA = Path("conversaciones_kommo.txt")
SELECTOR_CHAT = ", ".join(
    (
        ".chats-list-item",
        ".chats-list__item",
        ".inbox-list__item",
        '[class*="chats-list-item"]',
        '[class*="inbox-list__item"]',
        '[data-entity="chat"]',
    )
)
SELECTOR_HISTORIAL = '.chat-history, [class*="chat-history"]'
SELECTOR_MENSAJE = ", ".join(
    (
        ".chat-message",
        ".feed-note",
        '[class*="chat-message"]',
        '[class*="message-item"]',
        '[data-entity="message"]',
    )
)
SELECTORES_NOMBRE = (
    ".chat-header__title",
    ".feed-header__name",
    ".chats__conversation-name",
    ".chat-title",
)
ITERACIONES_SCROLL = 15
PAUSA_SCROLL_MS = 1_500
PAUSA_ESPERA_MS = 10_000
MAXIMO_CHATS = 5_000


def argumentos() -> argparse.Namespace:
    """Lee la fecha inicial; por defecto usa el 1 de septiembre del año actual."""
    predeterminada = date.today().replace(month=9, day=1).isoformat()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--desde",
        type=date.fromisoformat,
        default=date.fromisoformat(predeterminada),
        metavar="AAAA-MM-DD",
        help=f"fecha inicial inclusiva (predeterminado: {predeterminada})",
    )
    return parser.parse_args()


async def primer_visible(page: Page, selector: str) -> Locator:
    """Devuelve el primer elemento visible que coincide con ``selector``."""
    elementos = page.locator(selector)
    for indice in range(await elementos.count()):
        elemento = elementos.nth(indice)
        if await elemento.is_visible():
            return elemento
    raise RuntimeError(f"No se encontró un elemento visible para: {selector}")


async def localizar_chats(page: Page) -> Locator:
    """Localiza las filas con clases conocidas o por su texto estable ``Lead #``."""
    candidatos = page.locator(SELECTOR_CHAT)
    for indice in range(await candidatos.count()):
        if await candidatos.nth(indice).is_visible():
            return candidatos
    return page.get_by_text(re.compile(r"^Lead #\d+$"))


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


async def cargar_historial(page: Page, historial: Optional[Locator] = None) -> None:
    """Carga mensajes antiguos desplazando el contenedor real del historial."""
    for _ in range(ITERACIONES_SCROLL):
        if historial is not None:
            await historial.evaluate("el => { el.scrollTop = 0; }")
        else:
            await page.evaluate(
                """selector => {
                    const visibles = [...document.querySelectorAll(selector)].filter(el => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    });
                    let el = visibles[0];
                    while (el) {
                        if (el.scrollHeight > el.clientHeight + 20) {
                            el.scrollTop = 0;
                            return true;
                        }
                        el = el.parentElement;
                    }
                    return false;
                }""",
                SELECTOR_MENSAJE,
            )
        await page.wait_for_timeout(PAUSA_SCROLL_MS)


async def desplazar_lista_chats(chat: Locator) -> bool:
    """Avanza la lista virtual de Kommo y devuelve si aún podía desplazarse."""
    return await chat.evaluate(
        """el => {
            let contenedor = el.parentElement;
            while (contenedor) {
                const estilo = getComputedStyle(contenedor);
                const desplazable = /(auto|scroll)/.test(estilo.overflowY);
                if (desplazable && contenedor.scrollHeight > contenedor.clientHeight + 20) {
                    const antes = contenedor.scrollTop;
                    const maximo = contenedor.scrollHeight - contenedor.clientHeight;
                    contenedor.scrollTop = Math.min(
                        maximo, antes + Math.max(200, contenedor.clientHeight * 0.8)
                    );
                    return contenedor.scrollTop > antes + 1;
                }
                contenedor = contenedor.parentElement;
            }
            return false;
        }"""
    )


def interpretar_fecha(valor: Optional[str]) -> Optional[date]:
    """Convierte fechas ISO o timestamps Unix encontrados en el DOM de Kommo."""
    if not valor:
        return None
    valor = valor.strip()
    try:
        numero = float(valor)
        if numero > 10_000_000_000:
            numero /= 1_000
        return datetime.fromtimestamp(numero).date()
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(valor[:10])
        except ValueError:
            return None


async def fecha_mensaje(mensaje: Locator) -> Optional[date]:
    """Busca la fecha en los atributos habituales del mensaje o de su ``time``."""
    for atributo in ("data-created-at", "data-timestamp", "data-time", "datetime"):
        encontrada = interpretar_fecha(await mensaje.get_attribute(atributo))
        if encontrada:
            return encontrada

    tiempos = mensaje.locator("time[datetime]")
    if await tiempos.count():
        return interpretar_fecha(await tiempos.first.get_attribute("datetime"))

    texto = (await mensaje.inner_text()).strip().lower()
    if re.search(r"\bhoy\b", texto):
        return date.today()
    if re.search(r"\bayer\b", texto):
        return date.fromordinal(date.today().toordinal() - 1)
    encontrada = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", texto)
    if encontrada:
        try:
            return date(*(int(parte) for parte in encontrada.groups()))
        except ValueError:
            pass
    return None


async def extraer_mensajes(
    page: Page, historial: Optional[Locator], desde: date
) -> tuple[list[str], int]:
    """Filtra mensajes fechados sin descartar contenido si Kommo oculta la fecha."""
    mensajes = historial.locator(SELECTOR_MENSAJE) if historial is not None else None
    if mensajes is None or await mensajes.count() == 0:
        mensajes = page.locator(SELECTOR_MENSAJE)

    textos = []
    sin_fecha = 0
    for indice in range(await mensajes.count()):
        mensaje = mensajes.nth(indice)
        if await mensaje.is_visible():
            fecha = await fecha_mensaje(mensaje)
            if fecha is None:
                sin_fecha += 1
            elif fecha < desde:
                continue
            texto = (await mensaje.inner_text()).strip()
            if texto:
                textos.append(texto)
    return textos, sin_fecha


def formatear_chat(nombre: str, mensajes: list[str]) -> str:
    """Construye el bloque que se añade al archivo de salida."""
    lineas = ["=" * 40, f"CHAT: {nombre}", "=" * 40]
    lineas.extend(mensajes or ["[Sin mensajes visibles]"])
    return "\n".join(lineas) + "\n\n"


def guardar_chat(nombre: str, mensajes: list[str]) -> None:
    """Añade inmediatamente un chat al archivo para conservar el progreso."""
    with ARCHIVO_SALIDA.open("a", encoding="utf-8") as archivo:
        archivo.write(formatear_chat(nombre, mensajes))


async def esperar_inicio_sesion(page: Page) -> None:
    """Espera la bandeja e informa periódicamente que el proceso sigue vivo."""
    transcurrido_ms = 0
    while True:
        try:
            chats = await localizar_chats(page)
            for indice in range(await chats.count()):
                if await chats.nth(indice).is_visible():
                    print("Bandeja detectada; comienza la exportación.", flush=True)
                    return
            await page.wait_for_timeout(PAUSA_ESPERA_MS)
        except Exception as error:
            raise RuntimeError(
                "Se perdió la conexión con la ventana de Kommo. No cierres la "
                "ventana del navegador mientras se ejecuta el programa."
            ) from error

        transcurrido_ms += PAUSA_ESPERA_MS
        segundos = transcurrido_ms // 1_000
        print(
            f"Sigo esperando la bandeja ({segundos} s). "
            "Puedes completar el inicio de sesión, pero no cierres el navegador.",
            flush=True,
        )


async def exportar(page: Page, desde: date) -> None:
    """Recorre también las conversaciones que Kommo carga al hacer scroll."""
    await esperar_inicio_sesion(page)

    ARCHIVO_SALIDA.write_text("", encoding="utf-8")
    print(f"Exportando todos los chats; Kommo cargará más al hacer scroll. Desde {desde}...")
    procesados: set[str] = set()
    errores = 0

    while len(procesados) < MAXIMO_CHATS:
        chats = await localizar_chats(page)
        ultimo_visible = None
        for indice in range(await chats.count()):
            chat = chats.nth(indice)
            if not await chat.is_visible():
                continue
            ultimo_visible = chat
            texto_fila = (await chat.inner_text()).strip()
            coincidencia = re.search(r"Lead #\d+", texto_fila)
            identificador = coincidencia.group(0) if coincidencia else texto_fila
            if not identificador or identificador in procesados:
                continue

            # Se marca antes de hacer clic: un chat defectuoso no bloquea el scroll.
            procesados.add(identificador)
            try:
                await chat.click()
                await page.wait_for_timeout(1_000)
                nombre = await nombre_chat(page, chat, len(procesados) - 1)
                try:
                    historial = await primer_visible(page, SELECTOR_HISTORIAL)
                except RuntimeError:
                    historial = None
                await cargar_historial(page, historial)
                mensajes, sin_fecha = await extraer_mensajes(page, historial, desde)
                guardar_chat(nombre, mensajes)
                if mensajes:
                    estado = f"Guardado: {nombre} ({len(mensajes)} mensajes)"
                else:
                    estado = f"Guardado: {nombre} (sin mensajes visibles desde {desde})"
                if sin_fecha:
                    estado += f"; {sin_fecha} mensajes sin fecha se conservaron"
                print(f"[{len(procesados)}] {estado}", flush=True)
            except Exception as error:  # un chat defectuoso no detiene los demás
                errores += 1
                print(f"[{len(procesados)}] Error en {identificador}: {error}", flush=True)

        if ultimo_visible is None:
            break
        avanzo = await desplazar_lista_chats(ultimo_visible)
        print(
            f"Buscando más conversaciones... {len(procesados)} revisadas.", flush=True
        )
        if not avanzo:
            break
        await page.wait_for_timeout(PAUSA_SCROLL_MS)

    print(
        f"Recorrido completo: {len(procesados)} conversaciones, {errores} errores.",
        flush=True,
    )


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


async def main(desde: date) -> None:
    """Abre una sesión persistente de Chromium y ejecuta la exportación."""
    DIRECTORIO_SESION.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        contexto = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(DIRECTORIO_SESION),
            headless=False,
            viewport={"width": 1440, "height": 900},
        )
        error_principal = None
        try:
            pagina = contexto.pages[0] if contexto.pages else await contexto.new_page()
            await abrir_bandeja(pagina)
            print(
                "Esperando la bandeja. Si es necesario, inicia sesión manualmente. "
                "Puedes minimizar la ventana, pero no la cierres.",
                flush=True,
            )
            await exportar(pagina, desde)
            print(f"Exportación terminada: {ARCHIVO_SALIDA.resolve()}")
        except Exception as error:
            error_principal = error
            raise
        finally:
            try:
                await contexto.close()
            except Exception as error:
                # Cerrar la ventana manualmente también corta el driver. No debe
                # ocultar el error útil que explica qué ocurrió primero.
                if error_principal is None:
                    print(f"El navegador ya estaba cerrado: {error}")


if __name__ == "__main__":
    asyncio.run(main(argumentos().desde))
