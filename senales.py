# senales.py
# FASE 2, paso 2: combinar los indicadores en UNA señal por día
# (COMPRAR / MANTENER / REDUCIR), con la razón escrita en lenguaje simple,
# y crear la página docs/senales.html con gráficos para revisarlas a ojo.
#
# Cómo se usa:   python senales.py
#
# Las señales se calculan sobre el S&P 500 (^GSPC). En las fases 3 y 4 se
# aplicarán al ETF SPY, que es el que se puede "comprar" (simuladamente).
#
# IMPORTANTE: la señal de un día usa el precio de CIERRE de ese día. Por eso
# solo se podría actuar al día SIGUIENTE. Lo tendremos en cuenta en la Fase 3
# para no hacer trampas ("look-ahead bias").

import html

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Patch

import almacen
import config
import indicadores as ind
from explorar import ESTILO, navegacion, eje_de_fechas, figura_a_html


# Color e icono de cada señal. El icono hace que la señal se entienda
# también sin distinguir colores (daltonismo, pantalla en blanco y negro).
ESTILO_SENAL = {
    "COMPRAR": {"color": "#1baf7a", "icono": "▲"},
    "MANTENER": {"color": "#8a8984", "icono": "■"},
    "REDUCIR": {"color": "#e34948", "icono": "▼"},
    "SIN DATOS": {"color": "#d0cfca", "icono": "·"},
}

# Días de bolsa en un mes (aprox.), para ver "qué pasó después".
DIAS_MES = 21


# ---------------------------------------------------------------------------
# LAS REGLAS
# ---------------------------------------------------------------------------

def tendencia(fila):
    # Mira el precio y las dos medias móviles:
    #   alcista: precio por encima de la media de 200 días Y la media de 50
    #            por encima de la de 200 (sube a corto y a largo plazo).
    #   bajista: lo contrario (precio y media de 50 por debajo de la de 200).
    #   mixta:   las pistas se contradicen.
    if fila.precio > fila.media_larga and fila.media_corta > fila.media_larga:
        return "alcista"
    if fila.precio < fila.media_larga and fila.media_corta < fila.media_larga:
        return "bajista"
    return "mixta"


def decidir(fila, corta=ind.MEDIA_CORTA, larga=ind.MEDIA_LARGA):
    # Recibe una fila de la tabla de indicadores y devuelve (señal, razón).
    # Las reglas van en orden: la primera que se cumple decide.
    # "corta" y "larga" (días de cada media) solo se usan en los textos.

    # Sin 200 días de historia todavía no hay media de 200 → no opinamos.
    # pd.isna() comprueba si un valor está vacío (NaN).
    if pd.isna(fila.media_larga) or pd.isna(fila.rsi):
        return "SIN DATOS", "Aún no hay 200 días de historia para calcular la tendencia."

    t = tendencia(fila)
    vix = f"el VIX está en zona «{fila.regimen}» ({fila.vix:.1f})"
    rsi = f"el RSI es {fila.rsi:.0f}"
    medias = (f"precio {fila.precio:,.0f}, media de {corta} días {fila.media_corta:,.0f}, "
              f"media de {larga} días {fila.media_larga:,.0f}")

    if t == "alcista":
        if fila.regimen == "pánico":
            return "MANTENER", (f"La tendencia es alcista ({medias}), pero {vix}: "
                                "con tanto miedo no conviene añadir más riesgo.")
        if fila.rsi >= ind.RSI_SOBRECOMPRA:
            return "MANTENER", (f"La tendencia es alcista ({medias}), pero {rsi}: ha subido muy "
                                "deprisa (sobrecompra). Mejor no perseguir el precio.")
        return "COMPRAR", (f"Tendencia alcista: el precio está por encima de la media de {larga} días "
                           f"y la media de {corta} por encima de la de {larga} ({medias}). Además {vix} "
                           f"y {rsi}, sin sobrecompra.")

    if t == "bajista":
        razon = (f"Tendencia bajista: el precio y la media de {corta} días están por debajo de la "
                 f"de {larga} ({medias}); {vix}.")
        if fila.rsi <= ind.RSI_SOBREVENTA:
            razon += (f" Ojo: {rsi} (sobreventa), puede haber rebotes, "
                      "pero la tendencia de fondo sigue siendo bajista.")
        return "REDUCIR", razon

    # Tendencia mixta: el VIX desempata.
    if fila.regimen in ("nervioso", "pánico"):
        return "REDUCIR", (f"La tendencia no está clara ({medias}) y {vix}: "
                           "incertidumbre alta, mejor reducir riesgo.")
    return "MANTENER", (f"La tendencia no está clara ({medias}), pero {vix}. "
                        "Sin motivo fuerte para comprar ni para vender: esperar.")


def calcular_senales(corta=ind.MEDIA_CORTA, larga=ind.MEDIA_LARGA, ajuste_vix=0, cierres=None):
    # Tabla con indicadores + señal + razón para cada día del histórico.
    # Los parámetros solo se cambian para las pruebas de robustez; "cierres"
    # permite pasar datos recortados (para comprobar que no se mira el futuro).
    if cierres is None:
        cierres = almacen.leer_cierres_diarios(["^GSPC", "^VIX"])
    tabla = ind.calcular_indicadores(cierres["^GSPC"], cierres["^VIX"], corta, larga, ajuste_vix)
    # .apply(..., axis=1) ejecuta "decidir" fila por fila.
    resultado = tabla.apply(decidir, axis=1, result_type="expand", corta=corta, larga=larga)
    tabla["senal"], tabla["razon"] = resultado[0], resultado[1]
    return tabla


# ---------------------------------------------------------------------------
# GRÁFICOS
# ---------------------------------------------------------------------------

def tramos(senales):
    # Agrupa días seguidos con la misma señal en "tramos" (inicio, fin, señal).
    # Truco: cada vez que la señal cambia, empieza un grupo nuevo; .cumsum()
    # va sumando 1 en cada cambio, así cada tramo tiene su número.
    grupo = (senales != senales.shift()).cumsum()
    resultado = []
    for _, dias in senales.groupby(grupo):
        resultado.append((dias.index[0], dias.index[-1], dias.iloc[0]))
    return resultado


def pintar_fondo(eje, tabla):
    # Colorea el fondo del gráfico según la señal de cada tramo de días.
    for inicio, fin, senal in tramos(tabla["senal"]):
        eje.axvspan(inicio, fin + pd.Timedelta(days=1),
                    color=ESTILO_SENAL[senal]["color"], alpha=0.22, linewidth=0)


def leyenda_senales(eje):
    marcas = [Patch(color=v["color"], alpha=0.45, label=f"{v['icono']} {k}")
              for k, v in ESTILO_SENAL.items() if k != "SIN DATOS"]
    eje.legend(handles=marcas, loc="upper left", frameon=False, fontsize=8, ncol=3)


def grafico_historico(tabla):
    # Todo el histórico del S&P 500 (escala log) con el fondo según la señal.
    figura, eje = plt.subplots(figsize=(7, 4))
    pintar_fondo(eje, tabla)
    eje.plot(tabla.index, tabla["precio"], color="#0b0b0b", linewidth=1, label="S&P 500")
    eje.plot(tabla.index, tabla["media_larga"], color="#2a78d6", linewidth=1, label="media 200 d")
    eje.set_yscale("log")
    # En escala log ponemos las marcas a mano para que se lean bien.
    eje.set_yticks([500, 1000, 2000, 4000, 8000])
    eje.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    eje.yaxis.set_minor_formatter(plt.NullFormatter())
    eje.set_title("S&P 500 y señal de cada día (todo el histórico)", loc="left")
    leyenda_senales(eje)
    eje_de_fechas(eje)
    return figura_a_html(figura, "S&P 500 desde 2007 con las señales coloreadas al fondo")


def grafico_reciente(tabla, anos=2):
    # Zoom a los últimos años: precio, medias de 50 y 200, y RSI debajo.
    reciente = tabla[tabla.index >= tabla.index[-1] - pd.DateOffset(years=anos)]
    figura, (eje, eje_rsi) = plt.subplots(
        2, 1, figsize=(7, 5.5), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    pintar_fondo(eje, reciente)
    eje.plot(reciente.index, reciente["precio"], color="#0b0b0b", linewidth=1.2, label="S&P 500")
    eje.plot(reciente.index, reciente["media_corta"], color="#eb6834", linewidth=1.2, label="media 50 d")
    eje.plot(reciente.index, reciente["media_larga"], color="#2a78d6", linewidth=1.2, label="media 200 d")
    eje.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    eje.set_title(f"Últimos {anos} años: precio, medias y señal", loc="left")
    # Dos leyendas: las líneas (abajo a la derecha) y los colores de señal.
    lineas = eje.legend(loc="lower right", frameon=False, fontsize=8)
    eje.add_artist(lineas)
    leyenda_senales(eje)

    pintar_fondo(eje_rsi, reciente)
    eje_rsi.plot(reciente.index, reciente["rsi"], color="#6250d6", linewidth=1)
    for nivel in (ind.RSI_SOBREVENTA, ind.RSI_SOBRECOMPRA):
        eje_rsi.axhline(nivel, color="#8a8984", linewidth=0.8, linestyle="--")
    eje_rsi.set_ylim(0, 100)
    eje_rsi.set_yticks([30, 70])
    eje_rsi.set_ylabel("RSI")
    eje_rsi.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
    eje_rsi.xaxis.set_major_formatter(mdates.DateFormatter("%m/%Y"))
    figura.tight_layout()
    return figura_a_html(figura, "Últimos dos años del S&P 500 con medias, RSI y señales")


# ---------------------------------------------------------------------------
# TABLAS
# ---------------------------------------------------------------------------

def tabla_que_paso_despues(tabla):
    # Para cada señal: % de días, y qué hizo el S&P 500 en el MES SIGUIENTE.
    # Aquí SÍ miramos el futuro (shift(-21) = precio dentro de 21 días),
    # pero solo para EVALUAR las señales, nunca para calcularlas.
    # No es un backtest: no hay comisiones ni operaciones. Eso es la Fase 3.
    futuro = tabla["precio"].shift(-DIAS_MES) / tabla["precio"] - 1
    validos = tabla.assign(futuro=futuro).dropna(subset=["futuro"])
    validos = validos[validos["senal"] != "SIN DATOS"]
    filas = []
    for senal in ["COMPRAR", "MANTENER", "REDUCIR"]:
        grupo = validos[validos["senal"] == senal]
        if grupo.empty:
            continue
        filas.append(
            f"<tr><td>{ESTILO_SENAL[senal]['icono']} {senal}</td>"
            f"<td>{len(grupo) / len(validos):.0%}</td>"
            f"<td>{grupo['futuro'].mean():+.2%}</td>"
            f"<td>{(grupo['futuro'] > 0).mean():.0%}</td>"
            f"<td>{grupo['futuro'].std():.2%}</td></tr>"
        )
    todos = validos["futuro"]
    filas.append(
        f"<tr><td><i>Todos los días</i></td><td>100%</td><td>{todos.mean():+.2%}</td>"
        f"<td>{(todos > 0).mean():.0%}</td><td>{todos.std():.2%}</td></tr>"
    )
    return "\n".join(filas)


def tabla_cambios(tabla, cuantos=12):
    # Los últimos cambios de señal, del más reciente al más antiguo.
    cambios = tabla[tabla["senal"] != tabla["senal"].shift()].iloc[1:]
    filas = []
    for fecha, fila in cambios.tail(cuantos).iloc[::-1].iterrows():
        e = ESTILO_SENAL[fila.senal]
        filas.append(
            f"<tr><td>{fecha:%d/%m/%Y}</td>"
            f"<td style='color:{e['color']};font-weight:700'>{e['icono']} {fila.senal}</td>"
            f"<td>{fila.precio:,.0f}</td><td>{fila.vix:.1f}</td></tr>"
        )
    # Los cambios que entran o salen de REDUCIR son los que implicarían
    # vender o volver a comprar. COMPRAR ↔ MANTENER no obliga a operar.
    anterior = tabla["senal"].shift()
    importantes = cambios[(cambios["senal"] == "REDUCIR") | (anterior[cambios.index] == "REDUCIR")]
    return "\n".join(filas), len(cambios), len(importantes)


# ---------------------------------------------------------------------------
# LA PÁGINA
# ---------------------------------------------------------------------------

def crear_pagina(tabla):
    hoy = tabla.iloc[-1]
    fecha_hoy = tabla.index[-1]
    e = ESTILO_SENAL[hoy.senal]
    filas_cambios, n_cambios, n_importantes = tabla_cambios(tabla)
    anos = (tabla.index[-1] - tabla.index[0]).days / 365.25
    origen = almacen.leer_metadato("origen", "desconocido")
    aviso = ("" if origen == "yahoo" else
             '<div class="aviso">⚠️ <b>DATOS SIMULADOS</b>: no saques conclusiones.</div>')

    pagina = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mercado EE.UU. – Fase 2: señales</title>
{ESTILO}
<style>
  .senal {{ font-size:2rem; font-weight:800; color:{e['color']}; }}
</style>
</head>
<body>
<main>
{navegacion("senales.html")}
<h1>Fase 2: señales</h1>
<div class="sub">Datos: {html.escape(origen)} · último cierre {fecha_hoy:%d/%m/%Y}</div>
{aviso}

<div class="tarjeta">
  <h2>Señal del último cierre</h2>
  <div class="senal">{e['icono']} {hoy.senal}</div>
  <p>{html.escape(hoy.razon)}</p>
  <table>
    <tr><th>Indicador</th><th>Valor</th></tr>
    <tr><td>S&amp;P 500</td><td>{hoy.precio:,.2f}</td></tr>
    <tr><td>Media 50 días</td><td>{hoy.media_corta:,.2f}</td></tr>
    <tr><td>Media 200 días</td><td>{hoy.media_larga:,.2f}</td></tr>
    <tr><td>RSI 14 días</td><td>{hoy.rsi:.1f}</td></tr>
    <tr><td>VIX</td><td>{hoy.vix:.2f} ({html.escape(hoy.regimen)})</td></tr>
  </table>
  <p class="sub">Señal calculada con el cierre de ese día: solo se podría actuar en la sesión siguiente.</p>
</div>

<div class="tarjeta">{grafico_historico(tabla)}
  <p class="sub">Verde = COMPRAR, gris = MANTENER, rojo = REDUCIR. Fíjate en 2008, 2020 y 2022:
  ¿aparece el rojo durante las caídas… o cuando ya han pasado?</p>
</div>

<div class="tarjeta">{grafico_reciente(tabla)}</div>

<div class="tarjeta">
  <h2>¿Qué pasó el mes siguiente?</h2>
  <table>
    <tr><th>Señal</th><th>% días</th><th>Mes siguiente</th><th>% subió</th><th>Disp.</th></tr>
    {tabla_que_paso_despues(tabla)}
  </table>
  <p class="sub">Media de lo que hizo el S&amp;P 500 en los {DIAS_MES} días de bolsa siguientes a cada señal,
  desde 2008. «Disp.» (dispersión o desviación típica) = cuánto varía el resultado: más alta, más
  sorpresas. <b>Esto no es un backtest</b> (sin comisiones ni operaciones reales): es solo para ver
  si las señales tienen sentido. La prueba seria es la Fase 3.</p>
</div>

<div class="tarjeta">
  <h2>Últimos cambios de señal</h2>
  <table>
    <tr><th>Fecha</th><th>Nueva señal</th><th>S&amp;P 500</th><th>VIX</th></tr>
    {filas_cambios}
  </table>
  <p class="sub">{n_cambios} cambios de señal en {anos:.0f} años. Pero pasar de COMPRAR a MANTENER
  (o al revés) no obliga a operar. Los que sí implicarían vender o volver a comprar son los que
  entran o salen de REDUCIR: {n_importantes} en {anos:.0f} años (unos {n_importantes / anos:.0f} al año),
  y cada uno costaría comisiones.</p>
</div>

<div class="tarjeta">
  <h2>Las reglas, en orden</h2>
  <details open><summary>Ver reglas</summary>
  <ol>
    <li><b>Tendencia alcista</b> (precio y media de 50 por encima de la de 200):
      <ul><li>VIX en pánico (&gt;30) → MANTENER</li>
          <li>RSI ≥ 70 (sobrecompra) → MANTENER</li>
          <li>si no → <b>COMPRAR</b></li></ul></li>
    <li><b>Tendencia bajista</b> (precio y media de 50 por debajo de la de 200) → <b>REDUCIR</b></li>
    <li><b>Tendencia mixta</b>: VIX nervioso o pánico (≥20) → REDUCIR; si no → MANTENER</li>
  </ol>
  </details>
</div>

<p class="sub">Solo análisis y simulación educativa. No es asesoramiento financiero.</p>
</main>
</body>
</html>
"""
    destino = config.CARPETA_WEB / "senales.html"
    destino.write_text(pagina, encoding="utf-8")
    return destino


if __name__ == "__main__":
    tabla = calcular_senales()
    hoy = tabla.iloc[-1]
    print(f"Último cierre ({tabla.index[-1]:%d/%m/%Y}): {hoy.senal}")
    print(f"  Razón: {hoy.razon}")
    print("\n% de días con cada señal:")
    print(tabla["senal"].value_counts(normalize=True).map("{:.1%}".format).to_string())
    print(f"\n✅ Página creada: {crear_pagina(tabla)}")
