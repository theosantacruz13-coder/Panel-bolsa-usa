# simulador.py
# FASE 4: simulador "en vivo" con dinero FICTICIO. Sin bróker, sin cuentas.
#
# Dos carteras de 10.000 USD en paralelo, para compararlas día a día:
#   - "completa": la estrategia de la Fase 2 (COMPRAR / MANTENER / REDUCIR).
#   - "spy":      comprar y mantener SPY (la referencia).
#
# Usa EXACTAMENTE las mismas reglas que el backtest (Fase 3):
#   - La señal se calcula con el cierre del día D.
#   - La orden se ejecuta en la APERTURA del día siguiente, con la misma
#     comisión, el mismo deslizamiento y acciones enteras.
#   - Sin stop-loss ni otras reglas que no estén en el backtest.
# Incluso usa la misma función de compra/venta: backtest.ejecutar_orden().
#
# Se ejecuta una vez al día, después del cierre (GitHub Actions). Cada vez:
#   1) Para cada día de bolsa YA CERRADO que falte por procesar:
#      a) ejecuta la orden pendiente al precio de APERTURA real de ese día;
#      b) calcula la señal al cierre y apunta la orden para el día siguiente;
#      c) guarda el valor de la cartera al cierre.
#   2) La orden queda guardada (y en git) antes de que abra el mercado al
#      día siguiente: así se puede comprobar que no se decidió "mirando".
#
# Cómo se usa:
#   python simulador.py ejecutar                 (lo hace GitHub cada día)
#   python simulador.py pausar     [completa|spy|todas]
#   python simulador.py reanudar   [completa|spy|todas]
#   python simulador.py reiniciar  [completa|spy|todas]
#   python simulador.py estado                   (resumen en pantalla)

import sqlite3
import sys
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo  # zonas horarias (viene con Python)

import pandas as pd

import backtest as bt
import config


# Cada estrategia: nombre visible, activo que opera y función de posición.
ESTRATEGIAS = {
    "completa": {"nombre": "Estrategia completa", "posicion": bt.estrategia_completa},
    "spy": {"nombre": "Comprar y mantener SPY", "posicion": bt.comprar_y_mantener},
}
ACTIVO = "SPY"

NUEVA_YORK = ZoneInfo("America/New_York")
APERTURA = time(9, 30)
# Consideramos "cerrado" un día a partir de las 16:30 de Nueva York (la bolsa
# cierra a las 16:00; el VIX publica su cierre a las 16:15).
DIA_CERRADO = time(16, 30)

BASE_DATOS = config.CARPETA_DATOS / "cartera.db"

ESQUEMA = """
-- Una fila por estrategia: su situación actual.
CREATE TABLE IF NOT EXISTS carteras (
    estrategia        TEXT PRIMARY KEY,
    estado            TEXT NOT NULL,      -- 'activa' o 'pausada'
    inicio            TEXT NOT NULL,      -- primer día de la simulación
    efectivo          REAL NOT NULL,
    acciones          INTEGER NOT NULL,
    costes            REAL NOT NULL,      -- comisiones + deslizamiento acumulados
    ultimo_dia        TEXT NOT NULL,      -- último día de bolsa procesado
    orden_objetivo    INTEGER,            -- orden pendiente: 1 dentro, 0 fuera, NULL ninguna
    orden_fecha_senal TEXT,               -- día cuyo cierre generó la orden
    orden_motivo      TEXT,               -- razón de la señal
    orden_registrada  TEXT                -- cuándo se guardó la orden (UTC)
);

-- Cada compra o venta ficticia.
CREATE TABLE IF NOT EXISTS operaciones (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    estrategia    TEXT NOT NULL,
    fecha         TEXT NOT NULL,          -- día en que se ejecuta (apertura)
    tipo          TEXT NOT NULL,          -- 'COMPRA' o 'VENTA'
    activo        TEXT NOT NULL,
    precio        REAL NOT NULL,          -- precio pagado/cobrado (con deslizamiento)
    cantidad      INTEGER NOT NULL,
    importe       REAL NOT NULL,
    comision      REAL NOT NULL,
    deslizamiento REAL NOT NULL,
    motivo        TEXT,
    fecha_senal   TEXT,                   -- día de la señal que la provocó
    registrada    TEXT,                   -- cuándo se decidió (UTC)
    recuperada    INTEGER NOT NULL        -- 1 = decidida DESPUÉS de esa apertura
);

-- Valor de cada cartera al cierre de cada día.
CREATE TABLE IF NOT EXISTS valores (
    estrategia TEXT NOT NULL,
    fecha      TEXT NOT NULL,
    efectivo   REAL NOT NULL,
    acciones   INTEGER NOT NULL,
    cierre     REAL NOT NULL,
    valor      REAL NOT NULL,
    PRIMARY KEY (estrategia, fecha)
);

-- Diario de lo que pasa: inicio, pausas, reinicios...
CREATE TABLE IF NOT EXISTS eventos (
    fecha_hora TEXT NOT NULL,
    estrategia TEXT NOT NULL,
    texto      TEXT NOT NULL
);
"""


def conectar(base=None):
    config.CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(base or BASE_DATOS)
    conexion.row_factory = sqlite3.Row  # filas accesibles por nombre: fila["efectivo"]
    conexion.executescript(ESQUEMA)
    return conexion


def ahora_utc():
    return datetime.now(timezone.utc)


def texto_utc(momento):
    return momento.strftime("%Y-%m-%d %H:%M:%S UTC")


def dias_cerrados(tabla, ahora):
    # Solo los días cuya sesión ya terminó. Si GitHub ejecuta esto con la
    # bolsa abierta, el día de hoy (con precios a medias) se ignora.
    limite = ahora.astimezone(NUEVA_YORK)
    cerrado = [datetime.combine(d.date(), DIA_CERRADO, NUEVA_YORK) <= limite for d in tabla.index]
    return tabla[cerrado]


def registrar_evento(conexion, estrategia, texto, ahora):
    conexion.execute("INSERT INTO eventos VALUES (?, ?, ?)", (texto_utc(ahora), estrategia, texto))


# ---------------------------------------------------------------------------
# EJECUCIÓN DIARIA
# ---------------------------------------------------------------------------

def procesar_estrategia(conexion, clave, tabla, ahora):
    # Avanza una estrategia por todos los días cerrados que le falten.
    posicion = ESTRATEGIAS[clave]["posicion"](tabla)
    fila = conexion.execute("SELECT * FROM carteras WHERE estrategia = ?", (clave,)).fetchone()

    if fila is None:
        # Primera vez: la cartera nace el último día cerrado. Ese día solo
        # se mira la señal; la primera compra será en la apertura siguiente.
        inicio = tabla.index[-1]
        conexion.execute(
            "INSERT INTO carteras VALUES (?, 'activa', ?, ?, 0, 0, ?, NULL, NULL, NULL, NULL)",
            (clave, f"{inicio:%Y-%m-%d}", float(bt.CAPITAL_INICIAL), f"{inicio - pd.Timedelta(days=1):%Y-%m-%d}"))
        registrar_evento(conexion, clave, f"Cartera creada con {bt.CAPITAL_INICIAL:,} USD ficticios", ahora)
        fila = conexion.execute("SELECT * FROM carteras WHERE estrategia = ?", (clave,)).fetchone()

    # El mismo "estado" que usa el backtest.
    estado = {"efectivo": fila["efectivo"], "acciones": fila["acciones"],
              "costes": fila["costes"], "abierta": None}
    orden = None
    if fila["orden_objetivo"] is not None:
        orden = {"objetivo": fila["orden_objetivo"], "fecha_senal": fila["orden_fecha_senal"],
                 "motivo": fila["orden_motivo"], "registrada": fila["orden_registrada"]}
    pausada = fila["estado"] == "pausada"
    pendientes = tabla[tabla.index > pd.Timestamp(fila["ultimo_dia"])]

    for fecha, dia in pendientes.iterrows():
        # a) Apertura: ejecutar la orden decidida el día anterior.
        if orden is not None and not pausada:
            movimiento = bt.ejecutar_orden(estado, orden["objetivo"], dia.apertura)
            if movimiento is not None:
                apertura_ny = datetime.combine(fecha.date(), APERTURA, NUEVA_YORK)
                registrada = datetime.strptime(orden["registrada"], "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
                conexion.execute(
                    "INSERT INTO operaciones (estrategia, fecha, tipo, activo, precio, cantidad, importe, "
                    "comision, deslizamiento, motivo, fecha_senal, registrada, recuperada) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (clave, f"{fecha:%Y-%m-%d}", movimiento["tipo"], ACTIVO, movimiento["precio"],
                     movimiento["cantidad"], movimiento["importe"], movimiento["comision"],
                     movimiento["deslizamiento"], orden["motivo"], orden["fecha_senal"],
                     orden["registrada"], int(registrada > apertura_ny)))
        orden = None

        # b) Cierre: mirar la señal y dejar la orden para mañana.
        objetivo = posicion.loc[fecha]
        if not pd.isna(objetivo) and not pausada:
            motivo = dia.razon if clave == "completa" else "Comprar y mantener: siempre invertido."
            orden = {"objetivo": int(objetivo), "fecha_senal": f"{fecha:%Y-%m-%d}",
                     "motivo": f"{dia.senal}: {motivo}" if clave == "completa" else motivo,
                     "registrada": texto_utc(ahora)}

        # c) Valor de la cartera al cierre.
        conexion.execute(
            "INSERT OR REPLACE INTO valores VALUES (?, ?, ?, ?, ?, ?)",
            (clave, f"{fecha:%Y-%m-%d}", estado["efectivo"], estado["acciones"], dia.cierre,
             estado["efectivo"] + estado["acciones"] * dia.cierre))

    if not pendientes.empty:
        conexion.execute(
            "UPDATE carteras SET efectivo = ?, acciones = ?, costes = ?, ultimo_dia = ?, "
            "orden_objetivo = ?, orden_fecha_senal = ?, orden_motivo = ?, orden_registrada = ? "
            "WHERE estrategia = ?",
            (estado["efectivo"], estado["acciones"], estado["costes"], f"{pendientes.index[-1]:%Y-%m-%d}",
             orden and orden["objetivo"], orden and orden["fecha_senal"],
             orden and orden["motivo"], orden and orden["registrada"], clave))
    return len(pendientes)


def ejecutar(base=None, tabla=None, ahora=None):
    # Paso diario. "tabla" y "ahora" solo se pasan en las pruebas.
    ahora = ahora or ahora_utc()
    tabla = bt.preparar_datos() if tabla is None else tabla
    tabla = dias_cerrados(tabla, ahora)
    resumen = {}
    with conectar(base) as conexion:
        for clave in ESTRATEGIAS:
            resumen[clave] = procesar_estrategia(conexion, clave, tabla, ahora)
    return resumen


# ---------------------------------------------------------------------------
# PAUSAR, REANUDAR Y REINICIAR
# ---------------------------------------------------------------------------

def elegir(cual, conexion):
    # Devuelve las estrategias a las que aplicar la acción (solo las que existen).
    if cual in (None, "todas"):
        claves = list(ESTRATEGIAS)
    elif cual in ESTRATEGIAS:
        claves = [cual]
    else:
        raise SystemExit(f"Estrategia desconocida: {cual}. Usa: {', '.join(ESTRATEGIAS)} o todas")
    existen = {f["estrategia"] for f in conexion.execute("SELECT estrategia FROM carteras")}
    for clave in claves:
        if clave not in existen:
            print(f"⚠️  La cartera '{clave}' todavía no existe: no se hace nada con ella.")
    return [c for c in claves if c in existen]


def pausar(cual=None, base=None, ahora=None):
    # Pausar = no se ejecutan ni se crean órdenes. Se cancela la pendiente.
    # La cartera se queda como está y su valor se sigue apuntando cada día.
    ahora = ahora or ahora_utc()
    with conectar(base) as conexion:
        for clave in elegir(cual, conexion):
            conexion.execute("UPDATE carteras SET estado = 'pausada', orden_objetivo = NULL, "
                             "orden_fecha_senal = NULL, orden_motivo = NULL, orden_registrada = NULL "
                             "WHERE estrategia = ?", (clave,))
            registrar_evento(conexion, clave, "Pausada (orden pendiente cancelada)", ahora)


def reanudar(cual=None, base=None, ahora=None):
    # Al reanudar, la siguiente señal (al cierre) vuelve a generar órdenes.
    ahora = ahora or ahora_utc()
    with conectar(base) as conexion:
        for clave in elegir(cual, conexion):
            conexion.execute("UPDATE carteras SET estado = 'activa' WHERE estrategia = ?", (clave,))
            registrar_evento(conexion, clave, "Reanudada", ahora)


def reiniciar(cual=None, base=None, ahora=None):
    # Borra todo de esa estrategia. En la siguiente ejecución empieza de
    # nuevo con 10.000 USD. El evento de reinicio se conserva.
    ahora = ahora or ahora_utc()
    with conectar(base) as conexion:
        for clave in elegir(cual, conexion):
            for tabla in ["carteras", "operaciones", "valores"]:
                conexion.execute(f"DELETE FROM {tabla} WHERE estrategia = ?", (clave,))
            registrar_evento(conexion, clave, "Reiniciada: se borró su historial", ahora)


# ---------------------------------------------------------------------------
# LECTURA (para la página y para el resumen)
# ---------------------------------------------------------------------------

def leer(base=None):
    with conectar(base) as conexion:
        carteras = {f["estrategia"]: dict(f) for f in conexion.execute("SELECT * FROM carteras")}
        operaciones = pd.read_sql_query("SELECT * FROM operaciones ORDER BY fecha, id", conexion)
        valores = pd.read_sql_query("SELECT * FROM valores ORDER BY fecha", conexion)
        eventos = pd.read_sql_query("SELECT * FROM eventos ORDER BY fecha_hora", conexion)
    return carteras, operaciones, valores, eventos


def mostrar_estado(base=None):
    carteras, operaciones, valores, _ = leer(base)
    if not carteras:
        print("Todavía no hay carteras. Ejecuta: python simulador.py ejecutar")
    for clave, c in carteras.items():
        v = valores[valores.estrategia == clave]
        valor = v["valor"].iloc[-1] if not v.empty else c["efectivo"]
        print(f"{ESTRATEGIAS[clave]['nombre']} ({c['estado']}), desde {c['inicio']}: "
              f"{valor:,.2f} USD ({valor / bt.CAPITAL_INICIAL - 1:+.2%}), "
              f"{c['acciones']} acciones, {c['efectivo']:,.2f} USD en efectivo, "
              f"{(operaciones.estrategia == clave).sum()} operaciones")


if __name__ == "__main__":
    accion = sys.argv[1] if len(sys.argv) > 1 else "estado"
    cual = sys.argv[2] if len(sys.argv) > 2 else None
    if accion == "ejecutar":
        for clave, dias in ejecutar().items():
            print(f"{ESTRATEGIAS[clave]['nombre']}: {dias} día(s) nuevo(s) procesado(s)")
    elif accion == "pausar":
        pausar(cual)
    elif accion == "reanudar":
        reanudar(cual)
    elif accion == "reiniciar":
        reiniciar(cual)
    elif accion != "estado":
        raise SystemExit(f"Acción desconocida: {accion}")
    mostrar_estado()
