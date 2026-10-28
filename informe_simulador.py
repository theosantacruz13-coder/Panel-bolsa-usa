# informe_simulador.py
# FASE 4: crea docs/simulador.html con el estado de las carteras ficticias.
# (El panel completo y bonito para el móvil será la Fase 5.)
#
# Cómo se usa:   python informe_simulador.py

import html

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

import backtest as bt
import config
import simulador as sim
from explorar import ESTILO, navegacion, figura_a_html

COLORES = {"completa": "#2a78d6", "spy": "#0b0b0b"}


def grafico_valores(valores):
    figura, eje = plt.subplots(figsize=(7, 3.6))
    for clave, grupo in valores.groupby("estrategia"):
        fechas = pd.to_datetime(grupo["fecha"])
        eje.plot(fechas, grupo["valor"], color=COLORES[clave], marker="o", markersize=3,
                 label=sim.ESTRATEGIAS[clave]["nombre"])
    eje.axhline(bt.CAPITAL_INICIAL, color="#8a8984", linewidth=0.8, linestyle="--")
    eje.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    eje.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    eje.legend(frameon=False, fontsize=8)
    eje.set_title("Valor de cada cartera ficticia (USD)", loc="left")
    return figura_a_html(figura, "Evolución del valor de las dos carteras simuladas")


def tarjeta(clave, cartera, valores):
    nombre = sim.ESTRATEGIAS[clave]["nombre"]
    v = valores[valores.estrategia == clave]
    valor = v["valor"].iloc[-1] if not v.empty else cartera["efectivo"]
    cierre = v["cierre"].iloc[-1] if not v.empty else None
    posicion = (f"{cartera['acciones']} acciones de SPY ({cartera['acciones'] * cierre:,.2f} USD)"
                if cartera["acciones"] and cierre else "fuera del mercado (todo en efectivo)")
    if cartera["orden_objetivo"] is None:
        orden = "ninguna"
    else:
        dentro = cartera["acciones"] > 0
        if cartera["orden_objetivo"] == 1:
            accion = "seguir DENTRO (no hace falta operar)" if dentro else "COMPRAR"
        else:
            accion = "VENDER todo" if dentro else "seguir FUERA (no hace falta operar)"
        orden = (f"{accion} en la apertura siguiente al {cartera['orden_fecha_senal']}. "
                 f"<span class='sub'>Registrada {html.escape(cartera['orden_registrada'])}. "
                 f"{html.escape(cartera['orden_motivo'] or '')}</span>")
    estado = "⏸️ PAUSADA" if cartera["estado"] == "pausada" else "▶️ activa"
    return f"""<div class="tarjeta">
  <h2>{html.escape(nombre)} <span class="sub">{estado}</span></h2>
  <div class="cifra">{valor:,.2f} USD</div>
  <div>{valor / bt.CAPITAL_INICIAL - 1:+.2%} desde el {cartera['inicio']}</div>
  <table>
    <tr><td>Posición</td><td>{posicion}</td></tr>
    <tr><td>Efectivo</td><td>{cartera['efectivo']:,.2f} USD</td></tr>
    <tr><td>Costes pagados</td><td>{cartera['costes']:,.2f} USD</td></tr>
    <tr><td>Último día procesado</td><td>{cartera['ultimo_dia']}</td></tr>
  </table>
  <p><b>Orden pendiente:</b> {orden}</p>
</div>"""


def crear_pagina(base=None):
    carteras, operaciones, valores, eventos = sim.leer(base)

    if not carteras:
        cuerpo = ('<div class="tarjeta"><p>Todavía no hay carteras. Se crearán en la próxima '
                  'ejecución diaria (o con <i>Actions → Actualizar datos → Run workflow</i>).</p></div>')
    else:
        tarjetas = "".join(tarjeta(c, carteras[c], valores) for c in sim.ESTRATEGIAS if c in carteras)
        dias = valores["fecha"].nunique()
        grafico = (grafico_valores(valores) if dias >= 2 else
                   "<p>El gráfico aparecerá cuando haya al menos 2 días de datos.</p>")

        # Diferencia entre las dos carteras, en puntos de rentabilidad.
        comparacion = ""
        ultimos = valores.sort_values("fecha").groupby("estrategia").last()
        if {"completa", "spy"} <= set(ultimos.index):
            diferencia = (ultimos.loc["completa", "valor"] - ultimos.loc["spy", "valor"]) / bt.CAPITAL_INICIAL
            comparacion = (f"<p><b>Estrategia completa frente a SPY: {diferencia:+.2%}</b> "
                           f"({dias} día(s) de bolsa simulados).</p>")

        filas_ops = "".join(
            f"<tr><td>{o.fecha}</td><td>{html.escape(sim.ESTRATEGIAS[o.estrategia]['nombre'])}</td>"
            f"<td>{o.tipo}{' ⚠️' if o.recuperada else ''}</td><td>{o.cantidad}</td>"
            f"<td>{o.precio:,.2f}</td><td>{o.comision:,.2f}</td>"
            f"<td class='sub' style='text-align:left'>{html.escape(o.motivo or '')}</td></tr>"
            for o in operaciones.iloc[::-1].itertuples())
        filas_eventos = "".join(
            f"<tr><td>{html.escape(e.fecha_hora)}</td><td>{html.escape(e.estrategia)}</td>"
            f"<td style='text-align:left'>{html.escape(e.texto)}</td></tr>"
            for e in eventos.iloc[::-1].itertuples())

        cuerpo = f"""{tarjetas}
<div class="tarjeta">
  <h2>Comparación en vivo</h2>
  {comparacion}
  {grafico}
  <p class="sub">Con pocos días, la diferencia es casi pura casualidad. Según el backtest, lo
  esperable es que la estrategia completa quede algo por detrás de SPY cuando el mercado sube, y
  que caiga menos en los mercados bajistas largos. Hacen falta meses o años para juzgarla.</p>
</div>
<div class="tarjeta">
  <h2>Operaciones</h2>
  <div class="scroll"><table>
    <tr><th>Fecha</th><th>Cartera</th><th>Tipo</th><th>Cant.</th><th>Precio</th><th>Comisión</th><th>Motivo</th></tr>
    {filas_ops or '<tr><td colspan="7">Ninguna todavía.</td></tr>'}
  </table></div>
  <p class="sub">Precio de apertura de SPY del día, con deslizamiento. ⚠️ = operación
  "recuperada": la orden se registró después de esa apertura porque GitHub se saltó alguna noche.
  El resultado es el mismo que habría salido a tiempo, pero esa decisión no quedó guardada antes.</p>
</div>
<div class="tarjeta">
  <h2>Diario de eventos</h2>
  <table><tr><th>Cuándo</th><th>Cartera</th><th>Qué</th></tr>{filas_eventos}</table>
</div>"""

    pagina = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mercado EE.UU. – Fase 4: simulador</title>
{ESTILO}
<style>
  .scroll {{ overflow-x:auto; }}
  .scroll table {{ min-width:620px; }}
</style>
</head>
<body>
<main>
{navegacion("simulador.html")}
<h1>Fase 4: simulador con dinero ficticio</h1>
<div class="sub">Sin bróker ni dinero real. Mismas reglas que el backtest: señal al cierre,
orden en la apertura siguiente, comisión {bt.COMISION:.2%} + deslizamiento {bt.DESLIZAMIENTO:.2%}.</div>
{cuerpo}
<p class="sub">Simulación educativa. No es asesoramiento financiero.</p>
</main>
</body>
</html>
"""
    destino = config.CARPETA_WEB / "simulador.html"
    destino.write_text(pagina, encoding="utf-8")
    return destino


if __name__ == "__main__":
    print(f"✅ Página creada: {crear_pagina()}")
