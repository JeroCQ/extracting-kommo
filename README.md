# Exportar conversaciones de Kommo con Playwright

Este proyecto abre la bandeja web de Kommo en un navegador real, recorre los
chats visibles, carga su historial mediante scroll y guarda los mensajes en
`conversaciones_kommo.txt`.

## Instalación

Requiere Python 3.9 o posterior. Instala Playwright y su navegador Chromium:

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## Ejecución

El archivo ya tiene permiso de ejecución, por lo que puede iniciarse con:

```bash
./extract.py
```

También se puede ejecutar mediante `python extract.py`.

El navegador usa `./kommo_session` como perfil persistente. En la primera
ejecución, inicia sesión manualmente cuando aparezca la ventana. El script
espera hasta 120 segundos a que la lista de chats sea visible; en ejecuciones
posteriores Kommo normalmente reutilizará la sesión guardada.

Para cada chat, el script:

1. abre la conversación;
2. desplaza el historial al inicio 15 veces, esperando 1,5 segundos cada vez;
3. obtiene el texto visible de los mensajes; y
4. lo añade inmediatamente a `conversaciones_kommo.txt` en UTF-8.

La escritura progresiva conserva los chats ya procesados si uno posterior
falla. Los errores individuales se muestran en la terminal y el recorrido
continúa con la siguiente conversación.

> **Importante:** la automatización depende de la estructura DOM de Kommo. Si
> Kommo cambia sus clases CSS, actualiza los selectores declarados al inicio de
> `extract.py`.

## Pruebas

```bash
python -m unittest -v
```
