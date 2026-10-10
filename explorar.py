# explorar.py
# FASE 1, paso 2: leer los datos guardados y crear una página web
# (docs/index.html) con gráficos y explicaciones, pensada para el móvil.
#
# Cómo se usa:   python explorar.py
# Luego abre docs/index.html en el navegador.
#
# Gráficos que crea:
#   1) Precio de cada índice en el tiempo (S&P 500, Dow Jones, Nasdaq).
#   2) Los tres índices en "base 100" para comparar cuánto ha crecido cada uno.
#   3) El VIX en el tiempo, coloreando las zonas calma/normal/nervioso/pánico.
#   4) Correlación VIX ↔ S&P 500: nube de puntos con los cambios diarios.
#   5) Correlación "móvil" de 1 año, para ver si la relación es estable.
#   6) La última sesión de SPY en velas de 5 minutos (intradía).

# "base64" convierte una imagen en texto, para meterla DENTRO del HTML
# (así la página es un único archivo que se ve igual en cualquier sitio).
import base64

# "io" nos deja guardar la imagen en memoria en lugar de en un archivo.
import io

# "html" escapa caracteres especiales (<, >, &) para escribir texto en HTML.
import html

# matplotlib es la librería clásica de gráficos en Python.
import matplotlib

matplotlib.use("Agg")  # dibujar sin ventana (en un servidor no hay pantalla)
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

import almacen
import config


# ---------------------------------------------------------------------------
# ESTILO DE LOS GRÁFICOS
# ---------------------------------------------------------------------------

# Un color fijo por índice (siempre el mismo en todos los gráficos).
COLORES = {"^GSPC": "#2a78d6", "^DJI": "#eb6834", "^IXIC": "#1baf7a", "^VIX": "#52514e"}

# Zonas del VIX que usaremos en la Fase 2: (desde, hasta, nombre, color de fondo).
ZONAS_VIX = [
    (0, 15, "calma (<15)", "#e8f1fb"),
    (15, 20, "normal (15-20)", "#f4f4f2"),
    (20, 30, "nervioso (20-30)", "#fdf0e0"),
    (30, 100, "pánico (>30)", "#fbe3e3"),
]

plt.rcParams.update({
    "figure.dpi": 110,
    "font.size": 10,
    "axes.spines.top": False,    # quitamos los bordes de arriba y derecha
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": "#e6e5e0",     # cuadrícula suave, que no moleste
    "grid.linewidth": 0.6,
    "axes.edgecolor": "#8a8984",
    "axes.titleweight": "bold",
    "lines.linewidth": 1.4,
})


def figura_a_html(figura, texto_alternativo):
    # Convierte una figura de matplotlib en una etiqueta <img> con la imagen
    # incrustada como texto base64.
    memoria = io.BytesIO()
    figura.savefig(memoria, format="png", bbox_inches="tight")
    plt.close(figura)  # liberamos memoria
    codigo = base64.b64encode(memoria.getvalue()).decode("ascii")
    return f'<img src="data:image/png;base64,{codigo}" alt="{html.escape(texto_alternativo)}">'


def eje_de_fechas(eje):
    # Pone en el eje X solo los años, para que no se amontonen las etiquetas.
    eje.xaxis.set_major_locator(mdates.YearLocator(base=3))
    eje.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))


# ---------------------------------------------------------------------------
# LOS GRÁFICOS
# ---------------------------------------------------------------------------

def grafico_indices(cierres):
    # Un gráfico pequeño por índice, uno debajo de otro ("small multiples").
    # Cada uno tiene su propia escala, porque el Dow (~40.000) y el S&P
    # (~5.000) son números muy distintos.
    indices = ["^GSPC", "^DJI", "^IXIC"]
    figura, ejes = plt.subplots(len(indices), 1, figsize=(7, 7), sharex=True)
    for eje, ticker in zip(ejes, indices):
        serie = cierres[ticker].dropna()
        eje.plot(serie.index, serie.values, color=COLORES[ticker])
        eje.set_title(config.NOMBRE_CORTO[ticker], loc="left", fontsize=10)
        eje.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    eje_de_fechas(ejes[-1])
    figura.suptitle("Precio de cada índice (puntos)", x=0.02, ha="left", fontweight="bold")
    figura.tight_layout()
    return figura_a_html(figura, "Precio del S&P 500, Dow Jones y Nasdaq en el tiempo")


def grafico_base_100(cierres):
    # "Base 100": dividimos cada serie por su primer valor y multiplicamos
    # por 100. Así todas empiezan en 100 y vemos quién ha crecido más,
    # sin importar que sus precios sean muy distintos.
    indices = ["^GSPC", "^DJI", "^IXIC"]
    datos = cierres[indices].dropna()
    base = datos / datos.iloc[0] * 100
    figura, eje = plt.subplots(figsize=(7, 3.8))
    for ticker in indices:
        eje.plot(base.index, base[ticker], color=COLORES[ticker], label=config.NOMBRE_CORTO[ticker])
        # Etiqueta directa al final de cada línea con su valor.
        eje.annotate(f"{base[ticker].iloc[-1]:.0f}", (base.index[-1], base[ticker].iloc[-1]),
                     xytext=(4, 0), textcoords="offset points", va="center",
                     fontsize=9, color="#0b0b0b")
    eje.axhline(100, color="#8a8984", linewidth=0.8, linestyle="--")
    eje.set_yscale("log")  # escala logarítmica: misma distancia = mismo % de subida
    eje.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    eje.legend(frameon=False, loc="upper left")
    eje.set_title(f"Crecimiento comparado (inicio {datos.index[0]:%Y} = 100, escala log)", loc="left")
    eje_de_fechas(eje)
    return figura_a_html(figura, "Índices en base 100 para comparar su crecimiento")


def grafico_vix(cierres):
    # El VIX con las zonas de régimen coloreadas al fondo.
    vix = cierres["^VIX"].dropna()
    figura, eje = plt.subplots(figsize=(7, 3.8))
    tope = max(vix.max() * 1.05, 35)
    for desde, hasta, nombre, color in ZONAS_VIX:
        eje.axhspan(desde, min(hasta, tope), color=color, zorder=0)
        eje.text(vix.index[0], (desde + min(hasta, tope)) / 2, f" {nombre}",
                 va="center", fontsize=8, color="#52514e")
    eje.plot(vix.index, vix.values, color=COLORES["^VIX"], linewidth=1)
    eje.set_ylim(0, tope)
    eje.set_title("VIX: el «índice del miedo»", loc="left")
    eje_de_fechas(eje)
    return figura_a_html(figura, "VIX en el tiempo con zonas de calma, normal, nervioso y pánico")


def grafico_dispersion(cambios, correlacion):
    # Nube de puntos: cada punto es un día. Eje X = cuánto cambió el VIX ese
    # día (%), eje Y = cuánto cambió el S&P 500 ese día (%).
    figura, eje = plt.subplots(figsize=(7, 4.5))
    eje.scatter(cambios["^VIX"] * 100, cambios["^GSPC"] * 100, s=8, alpha=0.35,
                color=COLORES["^GSPC"], edgecolors="none")
    eje.axhline(0, color="#8a8984", linewidth=0.8)
    eje.axvline(0, color="#8a8984", linewidth=0.8)
    eje.set_xlabel("Cambio diario del VIX (%)")
    eje.set_ylabel("Cambio diario del S&P 500 (%)")
    eje.set_title(f"Cada punto es un día · correlación = {correlacion:+.2f}", loc="left")
    return figura_a_html(figura, "Dispersión de cambios diarios del VIX frente al S&P 500")


def grafico_correlacion_movil(cambios):
    # Correlación calculada solo con los últimos 252 días (≈ 1 año de bolsa),
    # día tras día. Nos dice si la relación es estable o cambia con el tiempo.
    movil = cambios["^VIX"].rolling(252).corr(cambios["^GSPC"]).dropna()
    figura, eje = plt.subplots(figsize=(7, 3.2))
    eje.plot(movil.index, movil.values, color=COLORES["^GSPC"])
    eje.axhline(0, color="#8a8984", linewidth=0.8)
    eje.set_ylim(-1, 1)
    eje.set_title("Correlación VIX ↔ S&P 500 en ventanas de 1 año", loc="left")
    eje_de_fechas(eje)
    return figura_a_html(figura, "Correlación móvil de un año entre VIX y S&P 500")


def grafico_intradia():
    # Última sesión de SPY con velas de 5 minutos (hora de Nueva York).
    spy = almacen.leer_intradia("SPY")
    if spy.empty:
        return "<p>Aún no hay datos intradía.</p>", None
    ultimo_dia = spy.index[-1].normalize()
    sesion = spy[spy.index.normalize() == ultimo_dia]
    figura, eje = plt.subplots(figsize=(7, 3.2))
    eje.plot(sesion.index, sesion["cierre"], color=COLORES["^GSPC"])
    eje.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    eje.set_title(f"SPY el {ultimo_dia:%d/%m/%Y}, velas de 5 min (hora de Nueva York)", loc="left")
    return figura_a_html(figura, "Precio de SPY durante la última sesión"), len(spy)


# ---------------------------------------------------------------------------
# TABLA RESUMEN
# ---------------------------------------------------------------------------

def tabla_resumen(cierres):
    # Para cada activo: último precio, cambio en 1 año y crecimiento anual medio.
    filas = []
    for ticker in config.TODOS:
        serie = cierres[ticker].dropna()
        ultimo = serie.iloc[-1]
        # Precio de hace ~1 año: el último disponible en o antes de esa fecha.
        hace_un_ano = serie[: serie.index[-1] - pd.DateOffset(years=1)].iloc[-1]
        cambio_1a = ultimo / hace_un_ano - 1
        anos = (serie.index[-1] - serie.index[0]).days / 365.25
        # Crecimiento anual compuesto (CAGR): el % fijo que, repetido cada
        # año, lleva del primer precio al último.
        cagr = (ultimo / serie.iloc[0]) ** (1 / anos) - 1
        anual = "—" if ticker == "^VIX" else f"{cagr:+.1%}"  # en el VIX no tiene sentido
        filas.append(
            f"<tr><td>{html.escape(config.NOMBRE_CORTO[ticker])}</td>"
            f"<td>{ultimo:,.2f}</td><td>{cambio_1a:+.1%}</td><td>{anual}</td></tr>"
        )
    return "\n".join(filas)


# ---------------------------------------------------------------------------
# LA PÁGINA
# ---------------------------------------------------------------------------

def crear_pagina():
    cierres = almacen.leer_cierres_diarios(list(config.TODOS))
    if cierres.empty:
        raise SystemExit("No hay datos. Ejecuta antes: python descargar_datos.py")

    # Cambio porcentual diario: (precio de hoy / precio de ayer) - 1.
    # .pct_change() lo calcula para toda la tabla de una vez.
    cambios = cierres[["^VIX", "^GSPC"]].dropna().pct_change().dropna()
    correlacion = cambios["^VIX"].corr(cambios["^GSPC"])

    origen = almacen.leer_metadato("origen", "desconocido")
    actualizado = almacen.leer_metadato("actualizado", "?")
    simulado = origen != "yahoo"
    aviso = (
        '<div class="aviso">⚠️ <b>DATOS SIMULADOS</b>: estos precios son inventados '
        "para probar el programa. No saques conclusiones de ellos.</div>"
        if simulado else ""
    )

    img_intradia, n_velas = grafico_intradia()
    vix_hoy = cierres["^VIX"].dropna().iloc[-1]
    zona_hoy = next(nombre for desde, hasta, nombre, _ in ZONAS_VIX if desde <= vix_hoy < hasta)

    pagina = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mercado EE.UU. – Fase 1</title>
<style>
  /* Colores como "variables" para poder cambiar a modo oscuro fácilmente */
  :root {{ --fondo:#f7f7f5; --tarjeta:#ffffff; --texto:#0b0b0b; --suave:#52514e; --borde:#e6e5e0; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --fondo:#121211; --tarjeta:#1a1a19; --texto:#f0efec; --suave:#c3c2b7; --borde:#2e2e2c; }}
  }}
  body {{ margin:0; background:var(--fondo); color:var(--texto);
         font:16px/1.5 system-ui, -apple-system, sans-serif; }}
  main {{ max-width:760px; margin:auto; padding:16px; }}
  h1 {{ font-size:1.4rem; margin:.2em 0; }}
  h2 {{ font-size:1.1rem; margin:0 0 .4em; }}
  .sub {{ color:var(--suave); font-size:.9rem; }}
  .tarjeta {{ background:var(--tarjeta); border:1px solid var(--borde); border-radius:12px;
             padding:14px; margin:14px 0; }}
  /* Las imágenes tienen fondo blanco: las ponemos sobre blanco también en modo oscuro */
  img {{ width:100%; height:auto; background:#fff; border-radius:8px; }}
  table {{ width:100%; border-collapse:collapse; font-size:.92rem; font-variant-numeric:tabular-nums; }}
  th, td {{ padding:6px 4px; border-bottom:1px solid var(--borde); text-align:right; }}
  th:first-child, td:first-child {{ text-align:left; }}
  .aviso {{ background:#fdecc8; color:#5a3d00; border-radius:10px; padding:12px; margin:12px 0; }}
  .cifra {{ font-size:2rem; font-weight:700; }}
  details summary {{ cursor:pointer; color:var(--suave); }}
</style>
</head>
<body>
<main>
<h1>Mercado de EE.UU. · Fase 1: exploración</h1>
<div class="sub">Datos: {html.escape(origen)} · actualizado {html.escape(actualizado)}</div>
{aviso}

<div class="tarjeta">
  <h2>VIX hoy</h2>
  <div class="cifra">{vix_hoy:.1f}</div>
  <div>Zona: <b>{html.escape(zona_hoy)}</b></div>
  <div class="sub">El VIX mide cuánta volatilidad (subidas y bajadas bruscas) espera el
  mercado en el S&amp;P 500 durante los próximos 30 días. Más alto = más miedo.</div>
</div>

<div class="tarjeta">
  <h2>Resumen</h2>
  <table>
    <tr><th>Activo</th><th>Último</th><th>1 año</th><th>Anual medio</th></tr>
    {tabla_resumen(cierres)}
  </table>
  <p class="sub">«Anual medio» = crecimiento anual compuesto desde {cierres.index[0]:%Y}.
  Los índices no incluyen dividendos; los ETF (SPY, QQQ, DIA) sí, porque usamos precios ajustados.</p>
</div>

<div class="tarjeta">{grafico_indices(cierres)}</div>

<div class="tarjeta">{grafico_base_100(cierres)}
  <p class="sub">En escala logarítmica, una subida del 10 % ocupa lo mismo arriba que abajo del gráfico.
  Por eso las caídas de 2008 o 2020 se ven en su tamaño real.</p>
</div>

<div class="tarjeta">{grafico_vix(cierres)}
  <p class="sub">El VIX sube de golpe en las crisis y baja despacio. Estas cuatro zonas serán
  la base de las señales en la Fase 2.</p>
</div>

<div class="tarjeta">
  <h2>¿Se mueven juntos el VIX y el S&amp;P 500?</h2>
  <div class="cifra">{correlacion:+.2f}</div>
  <p>La <b>correlación</b> va de −1 a +1. +1: suben y bajan siempre a la vez. −1: cuando uno sube,
  el otro baja. 0: no hay relación. Un valor de {correlacion:+.2f} significa que
  {"cuando el VIX sube, el S&amp;P 500 suele bajar, y al revés" if correlacion < -0.3 else "la relación es débil"}.</p>
  {grafico_dispersion(cambios, correlacion)}
  {grafico_correlacion_movil(cambios)}
  <p class="sub">Usamos los <i>cambios diarios</i> y no los precios, porque dos cosas que suben con el
  tiempo parecen relacionadas aunque no lo estén (correlación «espuria»).</p>
</div>

<div class="tarjeta">{img_intradia}
  <p class="sub">{n_velas or 0} velas de 5 minutos de SPY guardadas en total.
  Yahoo solo da los últimos ~60 días; cada nueva descarga acumula más.</p>
</div>

<p class="sub">Solo análisis y simulación educativa. No es asesoramiento financiero.</p>
</main>
</body>
</html>
"""
    config.CARPETA_WEB.mkdir(parents=True, exist_ok=True)
    destino = config.CARPETA_WEB / "index.html"
    destino.write_text(pagina, encoding="utf-8")
    print(f"✅ Página creada: {destino}")
    print(f"   Correlación diaria VIX ↔ S&P 500: {correlacion:+.2f}")
    if simulado:
        print("   ⚠️  OJO: los datos son SIMULADOS.")


if __name__ == "__main__":
    crear_pagina()
