# simulador-bolsa-usa

Sistema **educativo** para analizar el mercado de acciones de EE.UU. y
**simular** inversiones con dinero ficticio. Está escrito en Python paso a paso,
con comentarios en español, y pensado para aprender desde cero.

> 🚫 **Sin bróker, sin cuentas, sin dinero real.** Solo se leen precios públicos
> y gratuitos de Yahoo Finance (librería `yfinance`, sin login). Todas las
> "compras" y "ventas" son simulaciones guardadas en archivos locales.

## Estado del proyecto

| Fase | Qué hace | Archivos | Estado |
|------|----------|----------|--------|
| 1 | Descarga de datos y exploración con gráficos | `config.py`, `almacen.py`, `descargar_datos.py`, `datos_ejemplo.py`, `explorar.py` | ✅ Hecha |
| 2 | Señales: régimen VIX, medias 50/200, RSI → COMPRAR / MANTENER / REDUCIR | `indicadores.py`, `senales.py` | ✅ Hecha |
| 3 | Backtesting honesto (comisiones, deslizamiento, entrenamiento/prueba, vs SPY) | — | ⏳ Pendiente |
| 4 | Simulador en tiempo real con cartera virtual de 10.000 USD | — | ⏳ Pendiente |
| 5 | Dashboard HTML para el móvil | — | ⏳ Pendiente |

## Activos que seguimos

| Ticker | Qué es |
|--------|--------|
| `^VIX` | Índice del miedo: volatilidad que espera el mercado para el S&P 500 |
| `^GSPC` | S&P 500: las 500 mayores empresas de EE.UU. |
| `^DJI` | Dow Jones: 30 grandes empresas |
| `^IXIC` | Nasdaq Composite: muchas tecnológicas |
| `SPY`, `QQQ`, `DIA` | ETF que copian al S&P 500, al Nasdaq-100 y al Dow Jones |

Los índices (`^`) no se pueden comprar: son solo un número. Los ETF sí, y son
los que usaremos en las simulaciones.

## Cómo está organizado

```
config.py            ← tickers, fechas y rutas (lo único que hay que tocar para cambiar algo)
almacen.py           ← guardar y leer precios en SQLite (lo usarán todas las fases)
descargar_datos.py   ← FASE 1: descarga precios REALES de Yahoo Finance
datos_ejemplo.py     ← FASE 1: genera precios INVENTADOS para probar sin internet
explorar.py          ← FASE 1: crea docs/index.html con gráficos y explicaciones
indicadores.py       ← FASE 2: régimen del VIX, medias móviles 50/200 y RSI
senales.py           ← FASE 2: reglas COMPRAR/MANTENER/REDUCIR y docs/senales.html
datos/mercado.db     ← base de datos SQLite (se crea al descargar)
datos/csv/           ← copia de los datos en CSV, un archivo por activo
docs/index.html      ← página de exploración (Fase 1)
docs/senales.html    ← página de señales (Fase 2)
.github/workflows/   ← automatización: GitHub descarga los datos por ti
```

Igual que en el repo `backtesting-btc`: un archivo por paso, constantes en
MAYÚSCULAS al principio, y un generador de datos de ejemplo para trabajar sin conexión.

## Cómo usarlo

### Opción A — desde el móvil, sin instalar nada (recomendada)

1. Abre el repositorio en GitHub → pestaña **Actions** → **Actualizar datos** →
   **Run workflow**.
2. Espera 2-3 minutos. Un ordenador de GitHub descarga los datos reales,
   crea la página y la guarda en el repo.
3. Además se repite solo de lunes a viernes tras el cierre de Wall Street.

### Opción B — en un ordenador

```bash
pip install -r requirements.txt   # instala las librerías (una sola vez)
python descargar_datos.py         # descarga los datos reales (1-2 minutos)
python explorar.py                # crea docs/index.html
python senales.py                 # crea docs/senales.html
```

Sin internet, puedes probar con datos inventados:

```bash
python datos_ejemplo.py
python explorar.py                # la página mostrará un aviso de DATOS SIMULADOS
```

## Las señales (Fase 2)

Se calculan cada día con el cierre del S&P 500 y el VIX. Las reglas se aplican en orden:

1. **Tendencia alcista** (precio y media de 50 días por encima de la de 200):
   VIX en pánico (>30) → MANTENER; RSI ≥ 70 (sobrecompra) → MANTENER; si no → **COMPRAR**.
2. **Tendencia bajista** (precio y media de 50 por debajo de la de 200) → **REDUCIR**.
3. **Tendencia mixta**: VIX ≥ 20 (nervioso o pánico) → REDUCIR; si no → MANTENER.

| Régimen VIX | calma | normal | nervioso | pánico |
|---|---|---|---|---|
| Valor | < 15 | 15-20 | 20-30 | > 30 |

La señal de un día usa el precio de cierre de ese día, así que solo se podría
actuar en la sesión siguiente (importante para no hacer trampas en la Fase 3).

## Datos que se guardan

**Tabla `diario`** (desde 2007, una fila por activo y día) y **tabla `intradia`**
(velas de 5 minutos, solo horario normal 9:30-16:00 de Nueva York):

| Columna | Significado |
|---------|-------------|
| `ticker` | Código del activo |
| `fecha` / `fecha_hora` | Día (`AAAA-MM-DD`) o día y hora de Nueva York (`AAAA-MM-DD HH:MM`) |
| `apertura`, `maximo`, `minimo`, `cierre` | Precios de la vela |
| `volumen` | Cantidad negociada |

- Los precios de los ETF están **ajustados por dividendos**: así comparar con
  "comprar y mantener" es justo, porque incluye lo que pagan.
- Yahoo solo da las velas de 5 minutos de los **últimos ~60 días**. Como se
  guardan con `INSERT OR REPLACE`, cada nueva descarga **acumula** más historia
  sin duplicar filas.

## Limitaciones honestas

- Yahoo Finance es gratuito pero no oficial: a veces falla o cambia sin avisar.
  El script reintenta 3 veces y dice qué activos no pudo descargar.
- Los precios "en tiempo real" de Yahoo pueden llevar unos minutos de retraso.
  Para una simulación educativa no importa, pero conviene saberlo.

⚠️ Proyecto de aprendizaje. Nada de esto es asesoramiento financiero.
