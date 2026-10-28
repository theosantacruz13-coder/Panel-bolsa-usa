# dashboard.py
# FASE 5: el PANEL principal (docs/index.html), pensado para el móvil.
# Junta en una sola pantalla:
#   - Estado del mercado: VIX y su régimen, S&P 500.
#   - Señal actual (COMPRAR / MANTENER / REDUCIR) y su razón.
#   - Las dos carteras ficticias del simulador y su resultado frente a SPY.
#   - Historial de operaciones.
#   - Lo que dijo el backtest, para poner el resultado en vivo en contexto.
#
# Cómo se usa:   python dashboard.py
#
# "Que se actualice sola": GitHub Actions rehace esta página cada noche, y la
# propia página se recarga cada 15 minutos si la tienes abierta. Además dice
# cuánto hace que se actualizó y avisa si los datos se han quedado viejos.

import html
import json

import pandas as pd

import almacen
import backtest as bt
import config
import simulador as sim
from explorar import ESTILO, navegacion
from senales import ESTILO_SENAL


# Régimen del VIX: (icono, color de fondo, color de texto). El icono permite
# distinguirlos sin depender del color.
ESTILO_REGIMEN = {
    "calma": ("●", "#e3f4ec", "#0b6b46"),
    "normal": ("●", "#eeeeec", "#3d3c39"),
    "nervioso": ("▲", "#fdf0d8", "#7a4a00"),
    "pánico": ("◆", "#fbe3e3", "#9b1c1c"),
}


def datos_mercado():
    # Señales e indicadores SOLO de días ya cerrados (si GitHub lo ejecuta con
    # la bolsa abierta, el día en curso tiene precios a medias).
    tabla = sim.dias_cerrados(bt.preparar_datos(), sim.ahora_utc())
    return tabla


def resumen_backtest(tabla):
    # Las cifras de referencia del backtest (Fase 3) con los mismos datos.
    resultado = {}
    for clave, info in sim.ESTRATEGIAS.items():
        m = bt.metricas(bt.simular(tabla, info["posicion"](tabla)))
        resultado[clave] = m
    return resultado


def pct(v, signo=True):
    return f"{v:+.1%}" if signo else f"{v:.1%}"


# ---------------------------------------------------------------------------
# PIEZAS DE LA PÁGINA
# ---------------------------------------------------------------------------

def bloque_mercado(tabla):
    hoy, ayer = tabla.iloc[-1], tabla.iloc[-2]
    icono, fondo, texto = ESTILO_REGIMEN[hoy.regimen]
    cambio_sp = hoy.precio / ayer.precio - 1
    cambio_vix = hoy.vix - ayer.vix
    e = ESTILO_SENAL[hoy.senal]
    return f"""<div class="fichas">
  <div class="ficha">
    <div class="etiqueta">VIX</div>
    <div class="cifra">{hoy.vix:.1f}</div>
    <div><span class="chip" style="background:{fondo};color:{texto}">{icono} {html.escape(hoy.regimen)}</span>
      <span class="sub">{cambio_vix:+.1f}</span></div>
  </div>
  <div class="ficha">
    <div class="etiqueta">S&amp;P 500</div>
    <div class="cifra">{hoy.precio:,.0f}</div>
    <div class="sub">{pct(cambio_sp)} en el día</div>
  </div>
  <div class="ficha ancha">
    <div class="etiqueta">Señal al cierre</div>
    <div class="cifra" style="color:{e['color']}">{e['icono']} {hoy.senal}</div>
    <div class="sub">{html.escape(hoy.razon)}</div>
  </div>
</div>"""


def bloque_carteras(carteras, valores):
    if not carteras:
        return ('<div class="tarjeta"><p>Las carteras ficticias se crearán en la próxima '
                'ejecución diaria.</p></div>')
    fichas = []
    for clave, info in sim.ESTRATEGIAS.items():
        if clave not in carteras:
            continue
        c = carteras[clave]
        v = valores[valores.estrategia == clave]
        valor = v["valor"].iloc[-1] if not v.empty else c["efectivo"]
        cierre = v["cierre"].iloc[-1] if not v.empty else 0
        posicion = (f"{c['acciones']} acc. SPY" if c["acciones"] else "en efectivo")
        pausa = " · ⏸️ pausada" if c["estado"] == "pausada" else ""
        fichas.append(f"""<div class="ficha">
    <div class="etiqueta"><span class="clave {clave}"></span>{html.escape(info['nombre'])}</div>
    <div class="cifra">{valor:,.0f} <span class="sub">USD</span></div>
    <div>{pct(valor / bt.CAPITAL_INICIAL - 1, True)} <span class="sub">desde {c['inicio']}</span></div>
    <div class="sub">{posicion} · efectivo {c['efectivo']:,.0f}{pausa}</div>
  </div>""")
    return '<div class="fichas">' + "".join(fichas) + "</div>"


def bloque_comparacion(valores):
    # Diferencia entre las carteras y datos para el gráfico interactivo.
    if valores.empty:
        return ""
    tabla = valores.pivot(index="fecha", columns="estrategia", values="valor").dropna()
    dias = len(tabla)
    texto = ""
    if {"completa", "spy"} <= set(tabla.columns) and dias:
        diferencia = (tabla["completa"].iloc[-1] - tabla["spy"].iloc[-1]) / bt.CAPITAL_INICIAL
        mejor = "por delante de" if diferencia > 0.0005 else "por detrás de" if diferencia < -0.0005 else "empatada con"
        texto = (f"<p>La estrategia completa va <b>{mejor}</b> comprar y mantener SPY: "
                 f"<b>{diferencia:+.2%}</b> tras {dias} día(s) de bolsa.</p>")
    if dias < 2:
        grafico = '<p class="sub">El gráfico aparecerá cuando haya al menos 2 días.</p>'
    else:
        datos = {
            "fechas": list(tabla.index),
            "series": [{"clave": c, "nombre": sim.ESTRATEGIAS[c]["nombre"],
                        "valores": [round(x, 2) for x in tabla[c]]}
                       for c in sim.ESTRATEGIAS if c in tabla.columns],
        }
        # JSON dentro de la página. "</" se escapa para que no pueda cerrar el <script>.
        datos_json = json.dumps(datos, ensure_ascii=False).replace("</", "<\\/")
        grafico = f"""<div id="grafico" class="grafico" role="img"
  aria-label="Valor diario de las dos carteras ficticias"></div>
<div class="leyenda">{''.join(f'<span><span class="clave {s["clave"]}"></span>{html.escape(s["nombre"])}</span>' for s in datos["series"])}</div>
<script id="datos-grafico" type="application/json">{datos_json}</script>"""
    return f"""<div class="tarjeta">
  <h2>Resultado frente a SPY</h2>
  {texto}
  {grafico}
  <p class="sub">Con pocos días la diferencia es casi pura casualidad. Mientras la señal sea
  COMPRAR, las dos carteras van prácticamente igual.</p>
</div>"""


def bloque_ordenes(carteras):
    filas = []
    for clave, info in sim.ESTRATEGIAS.items():
        c = carteras.get(clave)
        if not c:
            continue
        if c["orden_objetivo"] is None:
            orden = "ninguna"
        elif c["orden_objetivo"] == 1:
            orden = "seguir dentro" if c["acciones"] else "COMPRAR en la próxima apertura"
        else:
            orden = "VENDER en la próxima apertura" if c["acciones"] else "seguir fuera"
        filas.append(f"<tr><td><span class='clave {clave}'></span>{html.escape(info['nombre'])}</td>"
                     f"<td>{orden}</td></tr>")
    if not filas:
        return ""
    return ('<div class="tarjeta"><h2>Órdenes para la próxima apertura</h2><table>'
            + "".join(filas) + "</table></div>")


def bloque_operaciones(operaciones, cuantas=10):
    if operaciones.empty:
        filas = '<tr><td colspan="5">Ninguna todavía.</td></tr>'
    else:
        filas = "".join(
            f"<tr><td>{o.fecha[8:]}/{o.fecha[5:7]}</td><td><span class='clave {o.estrategia}'></span>"
            f"{'Estrategia' if o.estrategia == 'completa' else 'SPY'}</td>"
            f"<td>{o.tipo}{' ⚠️' if o.recuperada else ''}</td><td>{o.cantidad}</td>"
            f"<td>{o.precio:,.2f}</td></tr>"
            for o in operaciones.iloc[::-1].head(cuantas).itertuples())
    return f"""<div class="tarjeta">
  <h2>Últimas operaciones</h2>
  <table><tr><th>Fecha</th><th>Cartera</th><th>Tipo</th><th>Cant.</th><th>Precio</th></tr>{filas}</table>
  <p class="sub">⚠️ = decidida después de esa apertura (ejecución tardía de GitHub).
  Detalle y motivos en <a href="simulador.html">Simulador</a>.</p>
</div>"""


def bloque_backtest(referencia, inicio):
    filas = "".join(
        f"<tr><td><span class='clave {c}'></span>{html.escape(sim.ESTRATEGIAS[c]['nombre'])}</td>"
        f"<td>{pct(m['retorno_anual'])}</td><td>{pct(m['caida_maxima'])}</td><td>{m['sharpe']:.2f}</td></tr>"
        for c, m in referencia.items())
    return f"""<div class="tarjeta">
  <h2>Qué esperar (backtest {inicio:%Y}-hoy)</h2>
  <table><tr><th>Cartera</th><th>Anual</th><th>Caída máx.</th><th>Sharpe</th></tr>{filas}</table>
  <p class="sub">La estrategia <b>no superó</b> a comprar y mantener en rentabilidad; su ventaja fue
  caer menos en los mercados bajistas largos. Ver <a href="backtest.html">Backtest</a> y
  <a href="verificacion.html">Verificación</a>.</p>
</div>"""


# ---------------------------------------------------------------------------
# GRÁFICO INTERACTIVO (SVG + un poco de JavaScript, sin librerías externas)
# ---------------------------------------------------------------------------

SCRIPT = r"""
<script>
// Hace cuánto se actualizó la página, y aviso si los datos son viejos.
(function () {
  var marca = document.getElementById("actualizado");
  var horas = (Date.now() - Date.parse(marca.dataset.iso)) / 36e5;
  var texto = horas < 1 ? "hace menos de 1 hora" :
              horas < 48 ? "hace " + Math.round(horas) + " h" :
              "hace " + Math.round(horas / 24) + " días";
  marca.textContent = texto;
  // Fines de semana incluidos, más de 4 días sin actualizar es raro.
  if (horas > 96) document.getElementById("viejo").hidden = false;
})();

// Gráfico de líneas con "mira": al tocar o pasar el dedo, una línea vertical
// busca el día más cercano y muestra el valor de las dos carteras.
(function () {
  var fuente = document.getElementById("datos-grafico");
  if (!fuente) return;
  var datos = JSON.parse(fuente.textContent);
  var caja = document.getElementById("grafico");
  var NS = "http://www.w3.org/2000/svg";
  // Tamaño parecido al de un móvil, para que el texto no quede diminuto.
  var ancho = 360, alto = 200, m = {izq: 46, der: 8, arr: 10, aba: 22};
  var todos = [];
  datos.series.forEach(function (s) { todos = todos.concat(s.valores); });
  var min = Math.min.apply(null, todos), max = Math.max.apply(null, todos);
  var margen = Math.max((max - min) * 0.1, 20);
  min -= margen; max += margen;
  var n = datos.fechas.length;
  function x(i) { return m.izq + (ancho - m.izq - m.der) * (n === 1 ? 0.5 : i / (n - 1)); }
  function y(v) { return m.arr + (alto - m.arr - m.aba) * (1 - (v - min) / (max - min)); }
  function el(nombre, attrs, padre) {
    var e = document.createElementNS(NS, nombre);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    (padre || svg).appendChild(e); return e;
  }
  var svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 " + ancho + " " + alto);
  caja.appendChild(svg);
  // Cuadrícula suave y eje con 4 valores.
  for (var k = 0; k <= 3; k++) {
    var v = min + (max - min) * k / 3;
    el("line", {x1: m.izq, x2: ancho - m.der, y1: y(v), y2: y(v), "class": "rejilla"});
    var t = el("text", {x: m.izq - 6, y: y(v) + 4, "text-anchor": "end", "class": "eje"});
    t.textContent = Math.round(v).toLocaleString("es");
  }
  [0, n - 1].forEach(function (i) {
    var t = el("text", {x: x(i), y: alto - 6, "text-anchor": i ? "end" : "start", "class": "eje"});
    t.textContent = datos.fechas[i].slice(5).split("-").reverse().join("/");
  });
  // Una línea por cartera.
  datos.series.forEach(function (s) {
    var d = s.valores.map(function (v, i) { return (i ? "L" : "M") + x(i) + " " + y(v); }).join(" ");
    el("path", {d: d, "class": "linea " + s.clave});
  });
  // Mira + puntos + etiqueta.
  var mira = el("line", {y1: m.arr, y2: alto - m.aba, "class": "mira", visibility: "hidden"});
  var puntos = datos.series.map(function (s) { return el("circle", {r: 4, "class": "punto " + s.clave, visibility: "hidden"}); });
  var globo = document.createElement("div");
  globo.className = "globo"; globo.hidden = true; caja.appendChild(globo);
  function mostrar(evento) {
    var r = svg.getBoundingClientRect();
    var px = (evento.clientX - r.left) * ancho / r.width;
    var i = Math.round((px - m.izq) / (ancho - m.izq - m.der) * (n - 1));
    i = Math.max(0, Math.min(n - 1, i));
    mira.setAttribute("x1", x(i)); mira.setAttribute("x2", x(i)); mira.setAttribute("visibility", "visible");
    // Contenido con textContent (los nombres no se interpretan como HTML).
    globo.textContent = "";
    var f = document.createElement("div"); f.className = "sub";
    f.textContent = datos.fechas[i].split("-").reverse().join("/"); globo.appendChild(f);
    datos.series.forEach(function (s, j) {
      puntos[j].setAttribute("cx", x(i)); puntos[j].setAttribute("cy", y(s.valores[i]));
      puntos[j].setAttribute("visibility", "visible");
      var fila = document.createElement("div");
      var clave = document.createElement("span"); clave.className = "clave " + s.clave;
      var valor = document.createElement("b");
      valor.textContent = s.valores[i].toLocaleString("es", {maximumFractionDigits: 0}) + " USD ";
      var nombre = document.createElement("span"); nombre.className = "sub"; nombre.textContent = s.nombre;
      fila.appendChild(clave); fila.appendChild(valor); fila.appendChild(nombre); globo.appendChild(fila);
    });
    globo.hidden = false;
    var izquierda = (x(i) / ancho) * r.width;
    globo.style.left = Math.min(Math.max(izquierda - 90, 0), r.width - 180) + "px";
  }
  function ocultar() {
    mira.setAttribute("visibility", "hidden"); globo.hidden = true;
    puntos.forEach(function (p) { p.setAttribute("visibility", "hidden"); });
  }
  svg.addEventListener("pointermove", mostrar);
  svg.addEventListener("pointerdown", mostrar);
  svg.addEventListener("pointerleave", ocultar);
})();
</script>
"""

ESTILO_PANEL = """<style>
  :root { --estrategia:#2a78d6; --spy:#0b0b0b; }
  @media (prefers-color-scheme: dark) { :root { --estrategia:#3987e5; --spy:#f0efec; } }
  .fichas { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin:14px 0; }
  .ficha { background:var(--tarjeta); border:1px solid var(--borde); border-radius:12px; padding:12px; min-width:0; }
  .ficha.ancha { grid-column:1 / -1; }
  .ficha .cifra { font-size:1.6rem; line-height:1.2; margin:2px 0; }
  .etiqueta { font-size:.8rem; color:var(--suave); text-transform:uppercase; letter-spacing:.03em; }
  .chip { display:inline-block; border-radius:999px; padding:1px 9px; font-size:.85rem; font-weight:600; }
  .clave { display:inline-block; width:14px; height:3px; border-radius:2px; margin-right:6px; vertical-align:middle; }
  .clave.completa { background:var(--estrategia); } .clave.spy { background:var(--spy); }
  .grafico { position:relative; touch-action:pan-y; }
  .grafico svg { width:100%; height:auto; display:block; }
  .rejilla { stroke:var(--borde); stroke-width:1; }
  .eje { fill:var(--suave); font-size:11px; }
  .linea { fill:none; stroke-width:2; } .linea.completa { stroke:var(--estrategia); } .linea.spy { stroke:var(--spy); }
  .mira { stroke:var(--suave); stroke-width:1; stroke-dasharray:3 3; }
  .punto { stroke:var(--tarjeta); stroke-width:2; } .punto.completa { fill:var(--estrategia); } .punto.spy { fill:var(--spy); }
  .globo { position:absolute; top:0; width:180px; background:var(--tarjeta); border:1px solid var(--borde);
           border-radius:8px; padding:6px 8px; font-size:.85rem; box-shadow:0 2px 8px rgba(0,0,0,.12); pointer-events:none; }
  .leyenda { display:flex; gap:14px; flex-wrap:wrap; font-size:.85rem; color:var(--suave); margin-top:4px; }
  a { color:var(--estrategia); }
</style>"""


def crear_pagina():
    tabla = datos_mercado()
    carteras, operaciones, valores, _ = sim.leer()
    referencia = resumen_backtest(tabla)
    ahora = sim.ahora_utc()
    origen = almacen.leer_metadato("origen", "desconocido")
    aviso = ("" if origen == "yahoo" else
             '<div class="aviso">⚠️ <b>DATOS SIMULADOS</b>: no saques conclusiones.</div>')

    pagina = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<!-- Recarga la página cada 15 minutos por si hay una versión nueva. -->
<meta http-equiv="refresh" content="900">
<title>Mercado EE.UU. – Panel</title>
{ESTILO}
{ESTILO_PANEL}
</head>
<body>
<main>
{navegacion("index.html")}
<h1>Panel del mercado de EE.UU.</h1>
<div class="sub">Último cierre {tabla.index[-1]:%d/%m/%Y} · actualizado
<span id="actualizado" data-iso="{ahora.isoformat()}">{ahora:%d/%m %H:%M} UTC</span></div>
<div id="viejo" class="aviso" hidden>⚠️ Los datos tienen más de 4 días: puede que la
actualización automática de GitHub haya fallado (pestaña Actions).</div>
{aviso}
{bloque_mercado(tabla)}
<h2>Carteras ficticias</h2>
{bloque_carteras(carteras, valores)}
{bloque_comparacion(valores)}
{bloque_ordenes(carteras)}
{bloque_operaciones(operaciones)}
{bloque_backtest(referencia, tabla.index[0])}
<p class="sub">Simulación educativa con dinero ficticio. Sin bróker. No es asesoramiento financiero.</p>
</main>
{SCRIPT}
</body>
</html>
"""
    destino = config.CARPETA_WEB / "index.html"
    destino.write_text(pagina, encoding="utf-8")
    return destino


if __name__ == "__main__":
    print(f"✅ Panel creado: {crear_pagina()}")
