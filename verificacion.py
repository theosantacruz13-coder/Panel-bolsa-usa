# verificacion.py
# FASE 3b: ¿son fiables los resultados de la Fase 3?
#
# Cómo se usa:   python verificacion.py      (tarda 1-2 minutos)
# Crea docs/verificacion.html y escribe un resumen en pantalla.
#
# Cuatro comprobaciones:
#   1) Periodos: qué años son entrenamiento y cuáles prueba.
#   2) Look-ahead bias: lo comprueban las pruebas de tests/ (aquí solo se
#      repite la comprobación principal para mostrarla en la página).
#   3) Robustez: repetir el backtest cambiando un poco los parámetros.
#   4) Walk-forward: elegir parámetros con 5 años y probar en el año siguiente.

import html
import itertools
import math

import matplotlib.pyplot as plt
import pandas as pd

import almacen
import backtest as bt
import config
from explorar import ESTILO, figura_a_html


# Variantes para la robustez (los valores del centro son los de siempre).
MEDIAS_CORTAS = [40, 50, 60]
MEDIAS_LARGAS = [180, 200, 220]
AJUSTES_VIX = [-2, 0, 2]            # mueve los límites 15/20/30 del VIX
VIX_ENTRADA = [18, 20, 22]          # para la variante "Solo VIX"
VIX_SALIDA = [28, 30, 32]

ANOS_DISENO = 5                     # walk-forward: 5 años para elegir...
PRIMER_ANO_PRUEBA = 2013            # ...y probar en el año siguiente (2013 = 2008-2012)


def pct(v):
    return "—" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:+.1%}"


# ---------------------------------------------------------------------------
# DATOS DE CADA VARIANTE
# ---------------------------------------------------------------------------

def tablas_variantes():
    # Calcula las señales de las 27 combinaciones (3 × 3 × 3).
    # Todas se recortan al mismo primer día que la versión normal, para
    # compararlas en igualdad de condiciones.
    base = bt.preparar_datos()
    tablas = {}
    for corta, larga, ajuste in itertools.product(MEDIAS_CORTAS, MEDIAS_LARGAS, AJUSTES_VIX):
        tabla = bt.preparar_datos(corta=corta, larga=larga, ajuste_vix=ajuste)
        tablas[(corta, larga, ajuste)] = tabla.loc[base.index[0]:]
    return base, tablas


def resumen_simulacion(tabla, posicion):
    resultado = bt.simular(tabla, posicion)
    m = bt.metricas(resultado)
    valor = resultado["valor"]
    fila = {"anual": m["retorno_anual"], "caida": m["caida_maxima"], "sharpe": m["sharpe"],
            "operaciones": m["operaciones"]}
    for crisis, fechas in bt.CRISIS.items():
        fila[crisis] = bt.caida_en_periodo(valor, *fechas)[0]
    prueba = bt.metricas(bt.simular(tabla, posicion, inicio=bt.INICIO_PRUEBA))
    fila["anual_prueba"] = prueba["retorno_anual"]
    fila["caida_prueba"] = prueba["caida_maxima"]
    return fila, valor


# ---------------------------------------------------------------------------
# 3) ROBUSTEZ
# ---------------------------------------------------------------------------

def robustez(tablas, base):
    filas = []
    for (corta, larga, ajuste), tabla in tablas.items():
        fila, _ = resumen_simulacion(tabla, bt.estrategia_completa(tabla))
        filas.append({"corta": corta, "larga": larga, "ajuste_vix": ajuste, **fila})
    completa = pd.DataFrame(filas)

    filas = []
    for entrada, salida in itertools.product(VIX_ENTRADA, VIX_SALIDA):
        fila, _ = resumen_simulacion(base, bt.estrategia_solo_vix(base, entrada, salida))
        filas.append({"entrada": entrada, "salida": salida, **fila})
    solo_vix = pd.DataFrame(filas)

    referencia, _ = resumen_simulacion(base, bt.comprar_y_mantener(base))
    return completa, solo_vix, referencia


# ---------------------------------------------------------------------------
# 4) WALK-FORWARD
# ---------------------------------------------------------------------------

def resultados_por_ano(valor):
    # Retorno y máxima caída de cada año natural, sobre una simulación continua.
    # El punto de partida de cada año es el último cierre del año anterior.
    filas = {}
    for ano in sorted(set(valor.index.year)):
        anterior = valor[valor.index.year < ano]
        tramo = valor[valor.index.year == ano]
        if anterior.empty:
            continue  # 2007 está incompleto: empezamos en 2008
        tramo = pd.concat([anterior.iloc[-1:], tramo])
        filas[ano] = {"retorno": tramo.iloc[-1] / tramo.iloc[0] - 1,
                      "caida": (tramo / tramo.cummax() - 1).min()}
    return pd.DataFrame(filas).T


def walk_forward(tablas, base):
    # Cada año de prueba Y: probamos las 27 combinaciones SOLO con los 5 años
    # anteriores (Y-5 … Y-1), elegimos la de mejor Sharpe y la usamos en Y.
    # Las posiciones de cada año se juntan en una sola simulación continua.
    ultimo_ano = base.index[-1].year
    posiciones = {clave: bt.estrategia_completa(t).reindex(base.index) for clave, t in tablas.items()}
    elegida = posiciones[(50, 200, 0)].copy()   # antes de 2013 usamos la normal
    elecciones = []
    for ano in range(PRIMER_ANO_PRUEBA, ultimo_ano + 1):
        desde, hasta = f"{ano - ANOS_DISENO}-01-01", f"{ano - 1}-12-31"
        puntuaciones = {}
        for clave, tabla in tablas.items():
            m = bt.metricas(bt.simular(tabla, posiciones[clave].loc[tabla.index], desde, hasta))
            puntuaciones[clave] = m["sharpe"]
        mejor = max(puntuaciones, key=puntuaciones.get)
        elecciones.append((ano, mejor))
        en_ano = base.index.year == ano
        elegida[en_ano] = posiciones[mejor][en_ano]

    wf_valor = bt.simular(base, elegida)["valor"]
    fijo_valor = bt.simular(base, bt.estrategia_completa(base))["valor"]
    spy_valor = bt.simular(base, bt.comprar_y_mantener(base))["valor"]
    anos = pd.concat({
        "walk_forward": resultados_por_ano(wf_valor),
        "fija": resultados_por_ano(fijo_valor),
        "spy": resultados_por_ano(spy_valor),
    }, axis=1)
    return anos, elecciones, {"walk_forward": wf_valor, "fija": fijo_valor, "spy": spy_valor}


# Diferencias menores de 0,5 puntos cuentan como empate (p. ej. años en los
# que la estrategia estuvo invertida igual que SPY y solo cambian las comisiones).
EMPATE = 0.005


def contar_victorias(anos, columna, desde_ano):
    # Devuelve (años, ganados, empatados) en retorno y en máxima caída.
    tramo = anos[anos.index >= desde_ano]
    resultado = [len(tramo)]
    for medida in ["retorno", "caida"]:
        # En la caída, "ganar" es caer menos (número menos negativo).
        diferencia = tramo[(columna, medida)] - tramo[("spy", medida)]
        resultado += [int((diferencia > EMPATE).sum()), int((diferencia.abs() <= EMPATE).sum())]
    return resultado


# ---------------------------------------------------------------------------
# GRÁFICOS
# ---------------------------------------------------------------------------

def grafico_robustez(completa, referencia):
    # Cada punto es una de las 27 variantes: retorno anual frente a máxima caída.
    figura, eje = plt.subplots(figsize=(7, 4))
    normal = completa[(completa.corta == 50) & (completa.larga == 200) & (completa.ajuste_vix == 0)]
    eje.scatter(completa["caida"] * 100, completa["anual"] * 100, s=30, color="#2a78d6",
                alpha=0.6, label="27 variantes de la estrategia completa")
    eje.scatter(normal["caida"] * 100, normal["anual"] * 100, s=90, facecolor="none",
                edgecolor="#2a78d6", linewidth=2, label="variante normal (50/200, VIX 15/20/30)")
    eje.scatter([referencia["caida"] * 100], [referencia["anual"] * 100], s=60, marker="s",
                color="#0b0b0b", label="Comprar y mantener SPY")
    eje.set_xlabel("Máxima caída (%)")
    eje.set_ylabel("Retorno anual (%)")
    eje.legend(frameon=False, fontsize=8, loc="lower left")
    eje.set_title("¿Cambia mucho el resultado con parámetros parecidos?", loc="left")
    return figura_a_html(figura, "Dispersión de resultados de las 27 variantes frente a SPY")


def grafico_anos(anos):
    # Barras por año: retorno de la estrategia fija y de SPY.
    figura, eje = plt.subplots(figsize=(7, 3.8))
    x = range(len(anos))
    eje.bar([i - 0.2 for i in x], anos[("fija", "retorno")] * 100, 0.4, color="#2a78d6", label="Estrategia completa")
    eje.bar([i + 0.2 for i in x], anos[("spy", "retorno")] * 100, 0.4, color="#0b0b0b", label="Comprar y mantener SPY")
    eje.set_xticks(list(x), [str(a)[2:] for a in anos.index], fontsize=8)
    eje.axhline(0, color="#8a8984", linewidth=0.8)
    eje.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    eje.legend(frameon=False, fontsize=8)
    eje.set_title("Retorno de cada año (20xx)", loc="left")
    return figura_a_html(figura, "Retorno anual de la estrategia y de SPY, año a año")


# ---------------------------------------------------------------------------
# LA PÁGINA
# ---------------------------------------------------------------------------

def rango(serie):
    return f"{pct(serie.min())} … {pct(serie.max())}"


def crear_pagina():
    base, tablas = tablas_variantes()
    _, resultados = bt.ejecutar_todo()
    completa, solo_vix, referencia = robustez(tablas, base)
    anos, elecciones, _ = walk_forward(tablas, base)

    normal = completa[(completa.corta == 50) & (completa.larga == 200) & (completa.ajuste_vix == 0)].iloc[0]
    n_wf, wf_ret, wf_ret_emp, wf_caida, wf_caida_emp = contar_victorias(anos, "walk_forward", PRIMER_ANO_PRUEBA)
    n_fija, fija_ret, fija_ret_emp, fija_caida, fija_caida_emp = contar_victorias(anos, "fija", anos.index[0])
    n_fija13, fija13_ret, fija13_ret_emp, fija13_caida, fija13_caida_emp = contar_victorias(
        anos, "fija", PRIMER_ANO_PRUEBA)
    supera_spy = (completa["anual"] > referencia["anual"]).sum()
    origen = almacen.leer_metadato("origen", "desconocido")
    inicio, fin = base.index[0], base.index[-1]
    ultimo_ano_parcial = fin.month < 12

    # --- tablas ---
    def fila_periodo(nombre, clave):
        r = resultados[nombre][clave]
        return (f"<td>{pct(r['retorno_anual'])}</td><td>{pct(r['caida_maxima'])}</td>"
                f"<td>{r['sharpe']:.2f}</td>")
    tabla_periodos = "".join(
        f"<tr><td>{n}</td>{fila_periodo(n, 'entrenamiento')}{fila_periodo(n, 'prueba')}</tr>"
        for n in ["Estrategia completa", "Comprar y mantener SPY"])

    filas_rob = "".join(
        f"<tr><td>{int(f.corta)}/{int(f.larga)}</td><td>{int(f.ajuste_vix):+d}</td><td>{pct(f.anual)}</td>"
        f"<td>{pct(f.caida)}</td><td>{f.sharpe:.2f}</td><td>{pct(f['Crisis financiera 2008'])}</td>"
        f"<td>{pct(f['COVID 2020'])}</td><td>{pct(f['Bajista 2022'])}</td></tr>"
        for _, f in completa.sort_values(["corta", "larga", "ajuste_vix"]).iterrows())

    columnas_resumen = [("anual", "Retorno anual"), ("caida", "Máxima caída"),
                        ("Crisis financiera 2008", "Caída 2008"), ("COVID 2020", "Caída 2020"),
                        ("Bajista 2022", "Caída 2022"), ("anual_prueba", "Anual en prueba (2017-)")]
    filas_resumen = "".join(
        f"<tr><td>{nombre}</td><td>{pct(normal[c])}</td><td>{rango(completa[c])}</td>"
        f"<td>{rango(solo_vix[c])}</td><td>{pct(referencia[c])}</td></tr>"
        for c, nombre in columnas_resumen)

    filas_anos = "".join(
        f"<tr><td>{ano}{'*' if ano == fin.year and ultimo_ano_parcial else ''}</td>"
        f"<td>{pct(f[('fija', 'retorno')])}</td><td>{pct(f[('spy', 'retorno')])}</td>"
        f"<td>{pct(f[('fija', 'caida')])}</td><td>{pct(f[('spy', 'caida')])}</td>"
        f"<td>{pct(f[('walk_forward', 'retorno')]) if ano >= PRIMER_ANO_PRUEBA else ''}</td>"
        f"<td>{pct(f[('walk_forward', 'caida')]) if ano >= PRIMER_ANO_PRUEBA else ''}</td></tr>"
        for ano, f in anos.iterrows())
    filas_elecciones = ", ".join(f"{a}: {c}/{l} VIX{v:+d}" for a, (c, l, v) in elecciones)

    pagina = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mercado EE.UU. – Fase 3b: verificación</title>
{ESTILO}
<style>
  .scroll {{ overflow-x:auto; }}
  .scroll table {{ min-width:560px; }}
</style>
</head>
<body>
<main>
<nav class="sub"><a href="index.html">Exploración</a> <a href="senales.html">Señales</a>
<a href="backtest.html">Backtest</a> <b>Verificación</b> <a href="simulador.html">Simulador</a></nav>
<h1>Fase 3b: ¿son fiables los resultados?</h1>
<div class="sub">Datos: {html.escape(origen)} · {inicio:%d/%m/%Y} → {fin:%d/%m/%Y}</div>

<div class="tarjeta">
  <h2>1. Entrenamiento y prueba</h2>
  <p><b>Entrenamiento</b>: {inicio:%d/%m/%Y} → 31/12/2016 (incluye <b>2008</b>).
  <b>Prueba</b>: 01/01/2017 → {fin:%d/%m/%Y} (incluye <b>2020</b> y <b>2022</b>).</p>
  <div class="scroll"><table>
    <tr><th rowspan="2">Estrategia</th><th colspan="3">Entrenamiento</th><th colspan="3">Prueba</th></tr>
    <tr><th>Anual</th><th>Caída</th><th>Sharpe</th><th>Anual</th><th>Caída</th><th>Sharpe</th></tr>
    {tabla_periodos}
  </table></div>
  <p class="sub">Ojo: las reglas no se ajustaron con estos datos, pero los parámetros (medias 50/200,
  RSI 14, VIX 20/30) son los clásicos de los libros, y se hicieron populares porque funcionaron en
  el pasado. Ningún periodo es del todo "nuevo" para ellos.</p>
</div>

<div class="tarjeta">
  <h2>2. Look-ahead bias</h2>
  <p>4 pruebas automáticas (<code>tests/test_sin_mirar_futuro.py</code>) comprueban que:</p>
  <ul>
    <li>Las señales del día D son idénticas si se borran todos los datos posteriores a D.</li>
    <li>La cartera hasta el día D no cambia si se duplican los precios futuros de SPY.</li>
    <li>Cada compra y venta ocurre el día de bolsa siguiente a la señal, al precio de apertura.</li>
    <li>Control: la versión con trampa sí compra un día antes (la prueba detecta el error).</li>
  </ul>
</div>

<div class="tarjeta">
  <h2>3. Robustez: 27 variantes</h2>
  <p>Medias {MEDIAS_CORTAS}/{MEDIAS_LARGAS} días y límites del VIX movidos −2, 0, +2 puntos.
  Para "Solo VIX": entrada {VIX_ENTRADA}, salida {VIX_SALIDA}.</p>
  {grafico_robustez(completa, referencia)}
  <div class="scroll"><table>
    <tr><th></th><th>Normal</th><th>Rango 27 variantes</th><th>Rango "Solo VIX" (9)</th><th>SPY</th></tr>
    {filas_resumen}
  </table></div>
  <p>Variantes que superan a SPY en retorno: <b>{supera_spy} de {len(completa)}</b>.</p>
  <details><summary>Ver las 27 variantes</summary>
  <div class="scroll"><table>
    <tr><th>Medias</th><th>VIX</th><th>Anual</th><th>Caída</th><th>Sharpe</th><th>2008</th><th>2020</th><th>2022</th></tr>
    {filas_rob}
  </table></div></details>
</div>

<div class="tarjeta">
  <h2>4. Walk-forward y año a año</h2>
  <p>Cada año desde {PRIMER_ANO_PRUEBA}: se elige la mejor de las 27 variantes con los
  {ANOS_DISENO} años anteriores y se usa solo en ese año.</p>
  <table>
    <tr><th>Años en que le ganó a SPY</th><th>En retorno</th><th>En máx. caída</th></tr>
    <tr><td>Walk-forward ({PRIMER_ANO_PRUEBA}-{fin.year}, {n_wf} años)</td>
        <td><b>{wf_ret}</b> (+{wf_ret_emp} empates)</td><td><b>{wf_caida}</b> (+{wf_caida_emp} empates)</td></tr>
    <tr><td>Estrategia normal, mismos años</td>
        <td><b>{fija13_ret}</b> (+{fija13_ret_emp} empates)</td><td><b>{fija13_caida}</b> (+{fija13_caida_emp} empates)</td></tr>
    <tr><td>Estrategia normal, 2008-{fin.year} ({n_fija} años)</td>
        <td><b>{fija_ret}</b> (+{fija_ret_emp} empates)</td><td><b>{fija_caida}</b> (+{fija_caida_emp} empates)</td></tr>
  </table>
  <p class="sub">Empate = diferencia menor de 0,5 puntos.</p>
  {grafico_anos(anos)}
  <div class="scroll"><table>
    <tr><th rowspan="2">Año</th><th colspan="2">Retorno</th><th colspan="2">Máx. caída</th><th colspan="2">Walk-forward</th></tr>
    <tr><th>Estrat.</th><th>SPY</th><th>Estrat.</th><th>SPY</th><th>Ret.</th><th>Caída</th></tr>
    {filas_anos}
  </table></div>
  <p class="sub">{'* Año incompleto. ' if ultimo_ano_parcial else ''}Variantes elegidas: {filas_elecciones}.</p>
</div>

<div class="tarjeta" style="border-left:4px solid #e34948">
  <h2>5. Conclusión</h2>
  <ul>
    <li><b>¿Hay trampas?</b> No se encontró look-ahead bias: las 4 pruebas pasan y no hubo que
    corregir nada.</li>
    <li><b>¿Es suerte de los parámetros?</b> Poco: con 27 variantes parecidas la caída de 2008 va
    de {pct(completa["Crisis financiera 2008"].min())} a {pct(completa["Crisis financiera 2008"].max())}
    y la máxima caída total de {pct(completa["caida"].min())} a {pct(completa["caida"].max())}.
    Los resultados de la estrategia completa son <b>estables</b>. "Solo VIX" no: su caída de 2022
    va de {pct(solo_vix["Bajista 2022"].min())} a {pct(solo_vix["Bajista 2022"].max())} según el
    umbral, es <b>frágil</b>.</li>
    <li><b>¿Gana a SPY?</b> {'No' if supera_spy == 0 else 'Casi nunca'}. {supera_spy} de {len(completa)} variantes superan a comprar y mantener en
    retorno, y solo ganó en retorno en {fija_ret} de {n_fija} años. Su ventaja es caer menos
    ({fija_caida} años con menor caída), sobre todo en mercados bajistas largos (2008, 2022).</li>
    <li><b>Ojo con 2008</b>: está en el periodo de entrenamiento, y las medias 50/200 son famosas
    precisamente porque esquivaron 2008. El −5 % es real en la simulación, pero es un solo episodio
    y no garantiza lo mismo en la próxima crisis (en 2020, rápida, cayó {pct(normal["COVID 2020"])}).</li>
  </ul>
</div>

<p class="sub">Simulación educativa con datos históricos. No es asesoramiento financiero.</p>
</main>
</body>
</html>
"""
    destino = config.CARPETA_WEB / "verificacion.html"
    destino.write_text(pagina, encoding="utf-8")
    return destino, completa, solo_vix, referencia, anos, elecciones


if __name__ == "__main__":
    destino, completa, solo_vix, referencia, anos, elecciones = crear_pagina()
    pd.set_option("display.width", 200)
    print(completa.round(3).to_string())
    print(solo_vix.round(3).to_string())
    print(pd.Series(referencia).round(3).to_string())
    print(anos.round(3).to_string())
    print(elecciones)
    for columna, desde in [("walk_forward", PRIMER_ANO_PRUEBA), ("fija", PRIMER_ANO_PRUEBA), ("fija", 2008)]:
        print(columna, desde, "→ (años, gana ret, empata ret, gana caída, empata caída):",
              contar_victorias(anos, columna, desde))
    print(f"✅ Página creada: {destino}")
