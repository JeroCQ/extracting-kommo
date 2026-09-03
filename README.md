# Exportar conversaciones de Kommo

## Qué significa el HTTP 403

Los eventos `incoming_chat_message` y `outgoing_chat_message` de WABA traen
únicamente un `id` y un `talk_id`; no traen el texto. El script usa el segundo
endpoint de Kommo, `GET /api/v4/talks/{talk_id}/messages`, para resolver esos
punteros. Que Events responda 200 **no** implica que el mismo token pueda leer
Talks. Un 403 en todos los talks indica que la integración no tiene autorizado
el acceso a chats/conversaciones.

En la configuración de la integración en Kommo, habilita el permiso de
chats/conversaciones, vuelve a autorizar la integración y guarda el token nuevo
como secreto de Colab con el nombre `KOMMO_KEY`. Los permisos de un token ya
emitido no se amplían automáticamente.

## Ejecutarlo en Google Colab

`test_extract.py` contiene pruebas para desarrolladores y **no debe pegarse en
una celda de Colab**. Su `import extract` presupone que el repositorio completo
está en el sistema de archivos; por eso una celda aislada produce
`ModuleNotFoundError: No module named 'extract'`.

1. Sube `extract.py` al panel **Files** de Colab.
2. Crea el secreto `KOMMO_KEY` y concede acceso al notebook.
3. Si la cuenta usa otro subdominio, define antes de ejecutar:

   ```python
   %env KOMMO_SUBDOMAIN=tu_subdominio
   ```

4. Ejecuta únicamente:

   ```python
   %run extract.py
   ```

El resultado se escribe en `mensajes_semana.txt`. Para descargarlo:

```python
from google.colab import files
files.download("mensajes_semana.txt")
```

## Ejecutarlo localmente

```bash
python -m pip install -r requirements.txt
export KOMMO_KEY='tu_token'
export KOMMO_SUBDOMAIN='tu_subdominio'
python extract.py
```
