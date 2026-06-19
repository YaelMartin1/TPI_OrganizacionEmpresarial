# Bot de Rendición de Gastos de Viaje (Simulador)

Implementa el flujo **TO-BE** del diagrama BPMN: el gerente carga cada
gasto en el momento en que ocurre, el bot valida contra presupuesto y
categoría, pre-aprueba automáticamente o deriva al director si el gasto
es extraordinario, y al finalizar el viaje el director aprueba la
rendición final.

## Cómo correrlo

```bash
python3 bot.py
```

No necesita librerías externas (usa solo `csv`, `os`, `datetime`,
`uuid`, `enum` de la librería estándar de Python 3).

## Manual de usuario rápido

| Comando | Qué hace |
|---|---|
| `gasto` | Inicia la carga de un nuevo gasto (fecha, monto, categoría, factura) |
| `saldo` | Muestra el presupuesto disponible del viaje |
| `cancelar` | Cancela la carga de gasto en curso y vuelve al inicio |
| `finalizar viaje` | Congela el dashboard y envía la rendición al director |
| `ayuda` | Muestra estos comandos |
| `salir` | Cierra la sesión de consola (el progreso queda guardado) |

Categorías de gasto válidas: `Alojamiento`, `Transporte`, `Comidas`, `Varios`.

Cuando un gasto **supera el saldo disponible**, el bot pregunta si se
quiere pedir una aprobación extraordinaria. Si se acepta, pide un
justificativo y luego simula el rol del director (escribís `aprobar`
o `rechazar` vos mismo, a modo de simulación de ese actor del BPMN).

## Diccionario de datos

### Tabla `presupuesto.csv` (1 fila por viaje)
| Campo | Tipo | Descripción |
|---|---|---|
| viaje_id | texto | Identificador único del viaje |
| gerente | texto | Nombre del gerente/director que viaja |
| presupuesto_total | numérico | Presupuesto asignado para el viaje |
| saldo_disponible | numérico | Presupuesto - gastos pre-aprobados/aprobados |
| estado_viaje | texto | `ABIERTO` / `FINALIZADO` |

### Tabla `gastos.csv` (1 fila por gasto cargado)
| Campo | Tipo | Descripción |
|---|---|---|
| gasto_id | texto | Identificador único del gasto |
| viaje_id | texto | Viaje al que pertenece |
| fecha | fecha (DD/MM/AAAA) | Fecha en que ocurrió el gasto |
| monto | numérico | Importe del gasto |
| categoria | texto | Alojamiento / Transporte / Comidas / Varios |
| tiene_factura | booleano (si/no) | Si se adjuntó comprobante |
| estado_aprobacion | texto | `PREAPROBADO` / `APROBADO` / `RECHAZADO` |
| tipo_aprobacion | texto | `NORMAL` / `EXTRAORDINARIO` / `EXTRAORDINARIO_RECHAZADO` |

### Tabla `estado_usuario.csv` (memoria del bot — máquina de estados)
| Campo | Tipo | Descripción |
|---|---|---|
| usuario | texto | Identificador del usuario (simula el chat_id de Telegram) |
| estado | texto | Estado actual dentro de la máquina de estados |
| gasto_temporal | texto | Datos parciales del gasto que se está cargando |

## Pruebas de estrés realizadas (camino infeliz)

1. Fecha con formato inválido (ej. `31/02/2026`) → el bot la rechaza y vuelve a pedirla.
2. Fecha futura → el bot la rechaza, pide la fecha real del gasto.
3. Texto en vez de número en el monto (ej. `cuatromil`) → error controlado, vuelve a pedir el monto.
4. Categoría inexistente o no aprobada (ej. `Viáticos`) → se informa la lista de categorías válidas.
5. Intentar registrar un gasto sin factura → se rechaza la carga hasta tener comprobante.
6. Gasto que supera el presupuesto disponible → deriva a flujo de aprobación extraordinaria.
7. Director rechaza la aprobación extraordinaria → el gasto queda registrado como `RECHAZADO`.
8. Respuesta ambigua en la aprobación del director (ni "aprobar" ni "rechazar") → se vuelve a solicitar.

## Cómo escalar esto a un bot real

La lógica de negocio (clase `GastoBot`) está totalmente desacoplada de
la consola. Para conectarlo a Telegram, solo hay que:

1. Reemplazar el `input()`/`print()` del `main()` por los handlers de
   `python-telegram-bot` (o `aiogram`).
2. Reemplazar los CSV por Google Sheets (API `gspread`) o una base SQL,
   sin tocar la clase `GastoBot`.
