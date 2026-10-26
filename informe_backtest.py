# informe_backtest.py
# FASE 3, paso 2: ejecuta todas las pruebas de backtest.py y crea la página
# docs/backtest.html con gráficos, tablas y conclusiones honestas.
#
# Cómo se usa:   python informe_backtest.py

import html

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import almacen
import backtest as bt
import config
from explorar import ESTILO, eje_de_fechas, figura_a_html


# Un color fijo por estrategia, el mismo en todos los gráficos.
COLORES = {
    "Estrategia completa": "#2a78d6",
    "Solo VIX": "#eb6834",
    "Comprar y mantener SPY": "#0b0b0b",
}
REFERENCIA = "Comprar y mantener SPY"


def pct(valor, signo=True):
    # Formatea un número como porcentaje: 0.123 → "+12.3%".
    if valor is None:
        return "—"
    return f"{valor:+.1%}" if signo else f"{valor:.1%}"


# ---------------------------------------------------------------------------
# GRÁFICOS
# ---------------------------------------------------------------------------

def grafico_valor(resultados):
    # Cuánto valdrían los 10.000 USD con cada estrategia (escala log).
    figura, eje = plt.subplots(figsize=(7, 4))
    for nombre, r in resultados.items():
        valor = r["completo"]["valor"]
        eje.plot(valor.index, valor.values, color=COLORES[nombre], label=nombre,
                 linewidth=1.6 if nombre != REFERENCIA else 1.2)
        eje.annotate(f"{valor.iloc[-1]:,.0f}", (valor.index[-1], valor.iloc[-1]),
                     xytext=(4, 0), textcoords="offset points", va="center", fontsize=8)
    eje.set_yscale("log")
    eje.set_yticks([5_000, 10_000, 20_000, 40_000, 80_000])
    eje.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    eje.yaxis.set_minor_formatter(plt.NullFormatter())
    eje.axhline(bt.CAPITAL_INICIAL, color="#8a8984", linewidth=0.8, linestyle="--")
    eje.legend(frameon=False, loc="upper left", fontsize=8)
    eje.set_title("Valor de la cartera (USD, escala log)", loc="left")
    eje_de_fechas(eje)
    return figura_a_html(figura, "Evolución de 10.000 USD con cada estrategia")


def grafico_caidas(resultados):
    # "Gráfico submarino": cuánto está cada cartera por debajo de su máximo.
    figura, eje = plt.subplots(figsize=(7, 3.6))
    for nombre, r in resultados.items():
        valor = r["completo"]["valor"]
        caida = (valor / valor.cummax() - 1) * 100
        eje.plot(caida.index, caida.values, color=COLORES[nombre], label=nombre, linewidth=1)
    eje.axhline(0, color="#8a8984", linewidth=0.8)
    eje.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    eje.legend(frameon=False, loc="lower right", fontsize=8)
    eje.set_title("Caída desde el máximo anterior (drawdown)", loc="left")
    eje_de_fechas(eje)
    return figura_a_html(figura, "Caídas desde máximos de cada estrategia")


def grafico_crisis(resultados):
    # Barras: máxima caída de cada estrategia en cada crisis.
    crisis = list(bt.CRISIS)
    nombres = list(resultados)
    ancho = 0.26
    posiciones = np.arange(len(crisis))  # 0, 1, 2
    figura, eje = plt.subplots(figsize=(7, 3.8))
    for i, nombre in enumerate(nombres):
        caidas = [resultados[nombre]["crisis"][c][0] * 100 for c in crisis]
        barras = eje.bar(posiciones + (i - 1) * ancho, caidas, ancho * 0.92,
                         color=COLORES[nombre], label=nombre)
        eje.bar_label(barras, fmt="%.0f%%", fontsize=8, padding=2)
    eje.set_xticks(posiciones, [c.replace(" ", "\n", 1) for c in crisis])
    eje.axhline(0, color="#8a8984", linewidth=0.8)
    eje.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    eje.set_ylim(min(eje.get_ylim()[0], -60), 5)
    eje.legend(frameon=False, loc="lower right", fontsize=8)
    eje.set_title("Máxima caída en cada crisis", loc="left")
    return figura_a_html(figura, "Máxima caída de cada estrategia en 2008, 2020 y 2022")


# ---------------------------------------------------------------------------
# TABLAS Y CONCLUSIONES
# ---------------------------------------------------------------------------

def tabla_metricas(resultados, clave="metricas"):
    filas = []
    for nombre, r in resultados.items():
        m = r[clave]
        filas.append(
            f"<tr><td>{html.escape(nombre)}</td>"
            f"<td>{m['valor_final']:,.0f}</td>"
            f"<td>{pct(m['retorno_total'])}</td>"
            f"<td>{pct(m['retorno_anual'])}</td>"
            f"<td>{pct(m['caida_maxima'])}</td>"
            f"<td>{m['sharpe']:.2f}</td>"
            f"<td>{m['operaciones']}</td>"
            f"<td>{pct(m['ganadoras'], signo=False)}</td>"
            f"<td>{m['tiempo_invertido']:.0%}</td></tr>"
        )
    return "\n".join(filas)


def tabla_crisis(resultados):
    filas = []
    for crisis, (desde, hasta) in bt.CRISIS.items():
        filas.append(f"<tr><th colspan='3' style='text-align:left'>{crisis} "
                     f"<span class='sub'>({desde[:7]} → {hasta[:7]})</span></th></tr>")
        for nombre, r in resultados.items():
            caida, ret = r["crisis"][crisis]
            filas.append(f"<tr><td>{html.escape(nombre)}</td><td>{pct(caida)}</td><td>{pct(ret)}</td></tr>")
    return "\n".join(filas)


def tabla_entreno_prueba(resultados):
    filas = []
    for nombre, r in resultados.items():
        e, p = r["entrenamiento"], r["prueba"]
        filas.append(
            f"<tr><td>{html.escape(nombre)}</td>"
            f"<td>{pct(e['retorno_anual'])}</td><td>{pct(e['caida_maxima'])}</td><td>{e['sharpe']:.2f}</td>"
            f"<td>{pct(p['retorno_anual'])}</td><td>{pct(p['caida_maxima'])}</td><td>{p['sharpe']:.2f}</td></tr>"
        )
    return "\n".join(filas)


def tabla_sobreajuste(ranking):
    # Las 5 mejores en entrenamiento + la versión por defecto (20/30).
    seleccion = ranking.head(5)
    por_defecto = ranking[(ranking["entrada"] == 20) & (ranking["salida"] == 30)]
    filas = []
    # pd.concat pega las dos tablas una debajo de otra.
    for _, f in pd.concat([seleccion, por_defecto]).iterrows():
        marca = " (por defecto)" if (f.entrada, f.salida) == (20, 30) else ""
        filas.append(
            f"<tr><td>VIX &lt; {f.entrada:g} / ≥ {f.salida:g}{marca}</td>"
            f"<td>{int(f.puesto_entrenamiento)}º</td><td>{f.sharpe_entrenamiento:.2f}</td>"
            f"<td>{int(f.puesto_prueba)}º</td><td>{f.sharpe_prueba:.2f}</td></tr>"
        )
    return "\n".join(filas)


def tabla_operaciones(resultados, cuantas=10):
    ops = resultados["Estrategia completa"]["completo"]["operaciones"]
    filas = []
    for o in reversed(ops[-cuantas:]):
        abierta = " (abierta)" if o.get("sigue_abierta") else ""
        filas.append(
            f"<tr><td>{o['entrada']:%d/%m/%Y}</td><td>{o['salida']:%d/%m/%Y}{abierta}</td>"
            f"<td>{o['precio_entrada']:,.2f}</td><td>{o['precio_salida']:,.2f}</td>"
            f"<td>{pct(o['resultado'])}</td></tr>"
        )
    return "\n".join(filas)


def conclusiones(resultados):
    # Frases automáticas y honestas comparando cada estrategia con SPY.
    ref = resultados[REFERENCIA]["metricas"]
    frases = []
    for nombre, r in resultados.items():
        if nombre == REFERENCIA:
            continue
        m = r["metricas"]
        gana_retorno = m["retorno_anual"] > ref["retorno_anual"]
        frases.append(
            f"<li><b>{html.escape(nombre)}</b>: "
            + ("<b>SUPERA</b>" if gana_retorno else "<b>NO supera</b>")
            + f" a comprar y mantener en rentabilidad ({pct(m['retorno_anual'])} al año frente a "
            f"{pct(ref['retorno_anual'])}). Su peor caída fue {pct(m['caida_maxima'])} frente a "
            f"{pct(ref['caida_maxima'])}"
            + (" (más suave)" if m["caida_maxima"] > ref["caida_maxima"] else " (peor)")
            + f", y su Sharpe {m['sharpe']:.2f} frente a {ref['sharpe']:.2f}"
            + (" (mejor rentabilidad por unidad de riesgo)." if m["sharpe"] > ref["sharpe"] else " (peor).")
            + "</li>"
        )
    return "\n".join(frases)


# ---------------------------------------------------------------------------
# LA PÁGINA
# ---------------------------------------------------------------------------

def crear_pagina():
    tabla, resultados = bt.ejecutar_todo()
    honesta, tramposa = bt.demo_look_ahead(tabla)
    ranking = bt.demo_sobreajuste(tabla)
    mejor = ranking.iloc[0]
    peor_entreno = ranking.sort_values("puesto_entrenamiento").iloc[-1]
    n = len(ranking)

    origen = almacen.leer_metadato("origen", "desconocido")
    aviso = ("" if origen == "yahoo" else
             '<div class="aviso">⚠️ <b>DATOS SIMULADOS</b>: no saques conclusiones.</div>')
    inicio, fin = tabla.index[0], tabla.index[-1]
    cabecera_metricas = ("<tr><th>Estrategia</th><th>Final (USD)</th><th>Total</th><th>Anual</th>"
                         "<th>Caída máx.</th><th>Sharpe</th><th>Oper.</th><th>% ganad.</th>"
                         "<th>% invert.</th></tr>")

    pagina = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mercado EE.UU. – Fase 3: backtest</title>
{ESTILO}
<style>
  .scroll {{ overflow-x:auto; }}
  .scroll table {{ min-width:560px; }}
  .veredicto {{ border-left:4px solid #e34948; }}
</style>
</head>
<body>
<main>
<nav class="sub"><a href="index.html">Exploración</a> <a href="senales.html">Señales</a> <b>Backtest</b></nav>
<h1>Fase 3: backtest honesto</h1>
<div class="sub">Datos: {html.escape(origen)} · {inicio:%d/%m/%Y} → {fin:%d/%m/%Y} ·
10.000 USD ficticios en SPY · comisión {bt.COMISION:.2%} + deslizamiento {bt.DESLIZAMIENTO:.2%} por operación</div>
{aviso}

<div class="tarjeta veredicto">
  <h2>Veredicto</h2>
  <ul>{conclusiones(resultados)}</ul>
  <p class="sub">El dinero fuera del mercado no cobra intereses en esta simulación. En la realidad
  (letras del Tesoro) habría ganado algo, sobre todo en 2023-2026: eso favorecería un poco a las
  estrategias que pasan tiempo fuera.</p>
</div>

<div class="tarjeta">{grafico_valor(resultados)}</div>

<div class="tarjeta">
  <h2>Resultados {inicio:%Y}-{fin:%Y}</h2>
  <div class="scroll"><table>{cabecera_metricas}{tabla_metricas(resultados)}</table></div>
  <p class="sub"><b>Caída máx.</b>: la peor bajada desde un máximo. <b>Sharpe</b>: rentabilidad
  dividida por la variabilidad (más alto = mejor relación beneficio/sustos). <b>% ganad.</b>:
  operaciones cerradas con beneficio. <b>% invert.</b>: % de días dentro del mercado.</p>
</div>

<div class="tarjeta">{grafico_caidas(resultados)}</div>

<div class="tarjeta">
  <h2>Las tres crisis</h2>
  {grafico_crisis(resultados)}
  <table><tr><th>Estrategia</th><th>Caída máx.</th><th>Retorno del periodo</th></tr>
  {tabla_crisis(resultados)}</table>
</div>

<div class="tarjeta">
  <h2>Entrenamiento y prueba</h2>
  <p>Dividimos la historia en dos: <b>entrenamiento</b> ({inicio:%Y}-2016), donde se permite
  diseñar y ajustar la estrategia, y <b>prueba</b> (2017-{fin:%Y}), que se guarda "bajo llave"
  para comprobar al final si funciona con datos que no ha visto. Cada periodo empieza con 10.000 USD.</p>
  <div class="scroll"><table>
    <tr><th rowspan="2">Estrategia</th><th colspan="3">Entrenamiento</th><th colspan="3">Prueba</th></tr>
    <tr><th>Anual</th><th>Caída</th><th>Sharpe</th><th>Anual</th><th>Caída</th><th>Sharpe</th></tr>
    {tabla_entreno_prueba(resultados)}
  </table></div>
</div>

<div class="tarjeta">
  <h2>Sobreajuste: un experimento</h2>
  <p>El <b>sobreajuste</b> ("overfitting") es ajustar una estrategia tanto a los datos del pasado
  que aprende su "ruido" (casualidades que no se repetirán). Funciona de maravilla en el pasado
  y decepciona en el futuro.</p>
  <p>Probamos {n} combinaciones de umbrales para "Solo VIX" (entrar cuando el VIX baja de X, salir
  cuando sube de Y) y las ordenamos por Sharpe en <b>entrenamiento</b>. ¿Mantienen el puesto en
  <b>prueba</b>?</p>
  <table><tr><th>Umbrales</th><th>Puesto entren.</th><th>Sharpe</th><th>Puesto prueba</th><th>Sharpe</th></tr>
  {tabla_sobreajuste(ranking)}</table>
  <p>La mejor en entrenamiento quedó <b>{int(mejor.puesto_prueba)}ª de {n}</b> en prueba. La peor en
  entrenamiento (VIX &lt; {peor_entreno.entrada:g} / ≥ {peor_entreno.salida:g}) quedó
  <b>{int(peor_entreno.puesto_prueba)}ª</b>. El orden del pasado casi no predice el del futuro: elegir
  "la mejor combinación" con datos pasados es sobre todo elegir la que tuvo más suerte.
  Por eso en este proyecto usamos los valores estándar (20/30, medias 50/200, RSI 14) sin afinarlos.</p>
</div>

<div class="tarjeta">
  <h2>Look-ahead bias: mirar el futuro sin querer</h2>
  <p>Es usar en una decisión un dato que en ese momento todavía no existía. Ejemplo típico:
  calcular la señal con el precio de cierre y "comprar" a ese mismo precio de cierre. En la
  realidad, cuando conoces el cierre ya no puedes comprar a ese precio.</p>
  <table>
    <tr><th>Estrategia completa</th><th>Anual</th><th>Caída máx.</th><th>Sharpe</th></tr>
    <tr><td>✅ Honesta (apertura del día siguiente)</td><td>{pct(honesta['retorno_anual'])}</td>
        <td>{pct(honesta['caida_maxima'])}</td><td>{honesta['sharpe']:.2f}</td></tr>
    <tr><td>⚠️ Con trampa (cierre del mismo día)</td><td>{pct(tramposa['retorno_anual'])}</td>
        <td>{pct(tramposa['caida_maxima'])}</td><td>{tramposa['sharpe']:.2f}</td></tr>
  </table>
  <p class="sub">Aquí la diferencia es pequeña porque las señales cambian despacio, pero el sesgo
  siempre juega a favor de la estrategia: con señales rápidas puede convertir una estrategia
  perdedora en "ganadora". Todas las cifras de esta página usan la versión honesta.</p>
</div>

<div class="tarjeta">
  <h2>Últimas operaciones (estrategia completa)</h2>
  <div class="scroll"><table>
    <tr><th>Compra</th><th>Venta</th><th>Precio compra</th><th>Precio venta</th><th>Resultado</th></tr>
    {tabla_operaciones(resultados)}
  </table></div>
  <p class="sub">Precios de SPY ajustados por dividendos, ya con deslizamiento. Resultado neto de comisiones.</p>
</div>

<p class="sub">Simulación educativa con datos históricos. Resultados pasados no garantizan
resultados futuros. No es asesoramiento financiero.</p>
</main>
</body>
</html>
"""
    destino = config.CARPETA_WEB / "backtest.html"
    destino.write_text(pagina, encoding="utf-8")
    return destino


if __name__ == "__main__":
    print(f"✅ Página creada: {crear_pagina()}")
