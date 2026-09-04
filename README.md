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

También se puede ejecutar mediante `python extract.py`. Para exportar desde el
1 de septiembre de 2026 hasta hoy, usa:

```bash
python extract.py --desde 2026-09-01
```

`--desde` es inclusivo: conserva los mensajes del día indicado y posteriores.
Si no indicas la opción, se usa el 1 de septiembre del año actual.

El navegador usa `./kommo_session` como perfil persistente. En la primera
ejecución, inicia sesión manualmente cuando aparezca la ventana. En ejecuciones
posteriores Kommo normalmente reutilizará la sesión guardada. Puedes completar
el inicio de sesión o abrir **Comunicaciones**, pero después no hace falta tocar
nada. La ventana se puede minimizar, aunque no se debe cerrar mientras el
programa trabaja.

Kommo puede continuar cargando recursos en segundo plano durante varios
minutos. El script inicia la navegación sin esperar toda esa actividad y usa
la aparición de la lista de chats como comprobación de que la bandeja está
lista.

Para cada chat, el script:

1. abre la conversación;
2. desplaza el historial al inicio 15 veces, esperando 1,5 segundos cada vez;
3. conserva los mensajes cuya fecha sea igual o posterior a `--desde`; y
4. lo añade inmediatamente a `conversaciones_kommo.txt` en UTF-8.

La escritura progresiva conserva los chats ya procesados si uno posterior
falla. Los errores individuales se muestran en la terminal y el recorrido
continúa con la siguiente conversación.

### Si la navegación es lenta

Si aparece `La navegación está tardando más de lo esperado`, no cierres la
ventana: termina el inicio de sesión, abre **Comunicaciones** si Kommo no lo hizo
automáticamente y espera. Mientras busca la bandeja, el script escribe un aviso
cada 10 segundos. Al encontrarla muestra `Bandeja detectada` y después informa
el avance de cada conversación como `[actual/total]`. La aparición de nuevo del
prompt `PS C:\...>` significa que el proceso ya terminó (correctamente o con un
error); mientras no reaparezca, sigue ejecutándose.

Si alguien cierra el navegador, se muestra un mensaje directo indicando que se
perdió la conexión, en lugar del error secundario `BrowserContext.close`.

Los nodos para los que Kommo no exponga una fecha se omiten para evitar incluir
mensajes anteriores al período solicitado, y el total omitido se informa en la
terminal.

> **Importante:** la automatización depende de la estructura DOM de Kommo. Si
> Kommo cambia sus clases CSS, actualiza los selectores declarados al inicio de
> `extract.py`.

## Pruebas

```bash
python -m unittest -v
```
