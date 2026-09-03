import time
import requests
from google.colab import userdata

SUBDOMINIO = "tanakasaludablecali"
TOKEN = userdata.get('KOMMO_KEY')

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

# Timestamp de hace 7 días
hace_7_dias = int(time.time()) - (7 * 24 * 3600)

print("Buscando eventos de mensajes de la última semana...")

# Uso del filtro 'from' para fechas
url_events = f"https://{SUBDOMINIO}.kommo.com/api/v4/events?filter[created_at][from]={hace_7_dias}&filter[type][]=incoming_chat_message&filter[type][]=outgoing_chat_message&limit=100"

res_events = requests.get(url_events, headers=headers)

if res_events.status_code == 204:
    print("No se registraron mensajes de chat en los últimos 7 días.")
elif res_events.status_code != 200:
    print(f"Error {res_events.status_code}: {res_events.text}")
else:
    eventos = res_events.json().get("_embedded", {}).get("events", [])
    print(f"Se encontraron {len(eventos)} eventos de mensajes esta semana.\n")

    mensajes_por_entidad = {}

    for ev in eventos:
        entity_id = ev.get("entity_id")
        entity_type = ev.get("entity_type")
        type_msg = "Cliente" if ev.get("type") == "incoming_chat_message" else "Asesor"
        
        value_after = ev.get("value_after", [])
        texto = ""
        if isinstance(value_after, list) and len(value_after) > 0:
            # Debugging: print the full value_after structure
            print(f"DEBUG: value_after for event {ev.get('id')}: {value_after}")
            print(f"DEBUG: message part: {value_after[0].get('message', {})}")
            texto = value_after[0].get("message", {}).get("text", "")
        
        # Debugging: print the extracted text
        print(f"DEBUG: Extracted text for event {ev.get('id')}: {texto}")

        if not texto:
            # Debugging: if text is empty, print the whole event to understand why
            print(f"DEBUG: Skipping event due to empty text: {ev}")
            continue

        key = f"{entity_type.upper()} ID: {entity_id}"
        if key not in mensajes_por_entidad:
            mensajes_por_entidad[key] = []
        
        mensajes_por_entidad[key].append(f"[{type_msg}]: {texto}")

    resultado_final = ""
    if not mensajes_por_entidad:
        print("No se pudieron extraer mensajes de los eventos encontrados.")
    else:
        for entidad, msgs in mensajes_por_entidad.items():
            bloque = f"========================================\n{entidad}\n========================================\n"
            bloque += "\n".join(msgs) + "\n\n"
            resultado_final += bloque
            print(bloque)

        with open("mensajes_semana.txt", "w", encoding="utf-8") as f:
            f.write(resultado_final)

        print("¡Proceso completado! Archivo 'mensajes_semana.txt' generado.")
