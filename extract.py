"""Exporta a texto las conversaciones de Kommo de los últimos días.

Los eventos de chat de API v4 solo contienen una referencia al mensaje
(`id` y `talk_id`). El texto se obtiene después desde el historial del talk.
"""

import os
import time

import requests


SUBDOMINIO = os.getenv("KOMMO_SUBDOMAIN", "tanakasaludablecali")
DIAS = 7
LIMITE = 250


class AccesoTalksDenegado(Exception):
    """El token es válido para Events, pero no está autorizado para Talks."""

    def __init__(self, talk_id, detalle=""):
        self.talk_id = talk_id
        self.detalle = detalle
        super().__init__(f"Acceso denegado al talk {talk_id}")


def obtener_token():
    """Obtiene el token de Colab o, fuera de Colab, de una variable de entorno."""
    token = os.getenv("KOMMO_KEY")
    if token:
        return token

    try:
        from google.colab import userdata
    except ImportError:
        return None
    return userdata.get("KOMMO_KEY")


def api_get(session, url, *, params=None, intentos=3):
    """Hace un GET con reintentos para rate limits y errores temporales."""
    for intento in range(intentos):
        respuesta = session.get(url, params=params, timeout=30)
        if respuesta.status_code not in (429, 500, 502, 503, 504):
            return respuesta
        espera = int(respuesta.headers.get("Retry-After", 2**intento))
        time.sleep(espera)
    return respuesta


def obtener_eventos(session, base_url, desde):
    """Pagina todos los eventos y devuelve las referencias de mensajes."""
    eventos = []
    pagina = 1
    while True:
        respuesta = api_get(
            session,
            f"{base_url}/api/v4/events",
            params={
                "filter[created_at][from]": desde,
                "filter[type][]": [
                    "incoming_chat_message",
                    "outgoing_chat_message",
                ],
                "limit": LIMITE,
                "page": pagina,
            },
        )
        if respuesta.status_code == 204:
            break
        respuesta.raise_for_status()
        lote = respuesta.json().get("_embedded", {}).get("events", [])
        eventos.extend(lote)
        if len(lote) < LIMITE:
            break
        pagina += 1
    return eventos


def referencia_mensaje(evento):
    """Extrae (talk_id, message_id) de las variantes conocidas de un evento."""
    value_after = evento.get("value_after") or []
    if isinstance(value_after, dict):
        value_after = [value_after]
    for cambio in value_after:
        mensaje = cambio.get("message", {}) if isinstance(cambio, dict) else {}
        if mensaje.get("talk_id") is not None and mensaje.get("id"):
            return str(mensaje["talk_id"]), str(mensaje["id"])
    return None, None


def obtener_historial(session, base_url, talk_id):
    """Obtiene todas las páginas del historial de un talk de Kommo."""
    mensajes = []
    pagina = 1
    while True:
        respuesta = api_get(
            session,
            f"{base_url}/api/v4/talks/{talk_id}/messages",
            params={"limit": LIMITE, "page": pagina},
        )
        if respuesta.status_code == 204:
            break
        if respuesta.status_code == 403:
            # Un 403 aquí no se arregla reintentando los demás talks: Events y
            # Talks tienen permisos distintos en Kommo.
            raise AccesoTalksDenegado(talk_id, respuesta.text[:500])
        respuesta.raise_for_status()
        lote = respuesta.json().get("_embedded", {}).get("messages", [])
        mensajes.extend(lote)
        if len(lote) < LIMITE:
            break
        pagina += 1
    return mensajes


def texto_mensaje(mensaje):
    """Devuelve texto legible, incluyendo una etiqueta para adjuntos sin texto."""
    texto = mensaje.get("text") or mensaje.get("message") or ""
    if isinstance(texto, dict):
        texto = texto.get("text") or texto.get("caption") or ""
    if str(texto).strip():
        return str(texto).strip()

    adjunto = mensaje.get("attachment") or mensaje.get("media")
    if adjunto:
        tipo = adjunto.get("type", "archivo") if isinstance(adjunto, dict) else "archivo"
        return f"[Adjunto: {tipo}]"
    return ""


def texto_en_evento(evento):
    """Compatibilidad con conectores que sí incluyen el cuerpo en el evento."""
    value_after = evento.get("value_after") or []
    if isinstance(value_after, dict):
        value_after = [value_after]
    for cambio in value_after:
        if not isinstance(cambio, dict):
            continue
        texto = texto_mensaje(cambio.get("message", {}))
        if texto:
            return texto
    return ""


def exportar_conversaciones(session, base_url, desde):
    """Cruza eventos con historiales y agrupa los mensajes por lead/talk."""
    eventos = obtener_eventos(session, base_url, desde)
    referencias = {}
    for evento in eventos:
        talk_id, message_id = referencia_mensaje(evento)
        if talk_id and message_id:
            referencias[message_id] = (talk_id, evento)

    # Algunos conectores incluyen texto y otros (como WABA) solo dejan el
    # puntero. Conservamos lo primero y consultamos Talks solo si hace falta.
    textos = {
        message_id: texto_en_evento(evento)
        for message_id, (_, evento) in referencias.items()
    }
    ids_pendientes = {message_id for message_id, texto in textos.items() if not texto}

    historiales = {}
    errores = []
    talks_pendientes = {
        talk_id
        for message_id, (talk_id, _) in referencias.items()
        if message_id in ids_pendientes
    }
    for talk_id in sorted(talks_pendientes):
        try:
            historiales[talk_id] = obtener_historial(session, base_url, talk_id)
        except AccesoTalksDenegado:
            # La autorización es de la integración, no de una conversación
            # concreta. Fallar pronto evita cientos de avisos idénticos.
            raise
        except requests.HTTPError as error:
            estado = error.response.status_code if error.response is not None else "?"
            errores.append(f"talk {talk_id}: HTTP {estado}")

    grupos = {}
    for message_id, (talk_id, evento) in referencias.items():
        texto = textos[message_id]
        mensaje = None
        if not texto:
            mensaje = next(
                (
                    item
                    for item in historiales.get(talk_id, [])
                    if str(item.get("id")) == message_id
                ),
                None,
            )
            texto = texto_mensaje(mensaje) if mensaje else ""
        if not texto:
            continue
        direccion = "Cliente" if evento.get("type") == "incoming_chat_message" else "Asesor"
        clave = (evento.get("entity_type", "lead").upper(), evento.get("entity_id"), talk_id)
        creado = evento.get("created_at") or (mensaje or {}).get("created_at", 0)
        grupos.setdefault(clave, []).append(
            (creado, direccion, texto)
        )

    return eventos, grupos, errores


def formatear(grupos):
    bloques = []
    for (tipo, entity_id, talk_id), mensajes in sorted(grupos.items()):
        lineas = [
            "=" * 40,
            f"{tipo} ID: {entity_id} | TALK ID: {talk_id}",
            "=" * 40,
        ]
        for _, direccion, texto in sorted(mensajes):
            lineas.append(f"[{direccion}]: {texto}")
        bloques.append("\n".join(lineas))
    return "\n\n".join(bloques) + ("\n" if bloques else "")


def main():
    token = obtener_token()
    if not token:
        raise SystemExit("No se encontró KOMMO_KEY en Colab userdata ni en el entorno.")

    desde = int(time.time()) - (DIAS * 24 * 3600)
    base_url = f"https://{SUBDOMINIO}.kommo.com"
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})

    print(f"Buscando eventos y conversaciones de los últimos {DIAS} días...")
    try:
        eventos, grupos, errores = exportar_conversaciones(session, base_url, desde)
    except AccesoTalksDenegado as error:
        print("\nKommo aceptó el token para Events, pero rechazó el acceso a Talks (HTTP 403).")
        print(f"La comprobación falló con el talk {error.talk_id}.")
        print(
            "Activa el permiso de chats/conversaciones en la integración de Kommo, "
            "vuelve a autorizarla y reemplaza KOMMO_KEY por el nuevo token."
        )
        print(
            "Los eventos WABA solo contienen id y talk_id; sin ese permiso Kommo no "
            "entrega el texto y el script no puede reconstruirlo."
        )
        if error.detalle:
            print(f"Detalle de Kommo: {error.detalle}")
        return
    except requests.HTTPError as error:
        detalle = error.response.text[:500] if error.response is not None else str(error)
        raise SystemExit(f"Kommo devolvió un error: {detalle}") from error

    print(f"Se encontraron {len(eventos)} eventos de mensajes.")
    for error in errores:
        print(f"Aviso: no se pudo leer {error}")

    resultado = formatear(grupos)
    if not resultado:
        print("No se obtuvo texto. Revisa que el token tenga acceso a Talks/Chats.")
        return

    with open("mensajes_semana.txt", "w", encoding="utf-8") as archivo:
        archivo.write(resultado)
    print(resultado)
    print("¡Proceso completado! Archivo 'mensajes_semana.txt' generado.")


if __name__ == "__main__":
    main()
