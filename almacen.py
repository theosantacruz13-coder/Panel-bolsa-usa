# almacen.py
# Funciones para GUARDAR y LEER precios en la base de datos SQLite.
# Las separamos en su propio archivo porque las usarán todas las fases:
# la descarga (Fase 1), las señales (Fase 2), el backtest (Fase 3)...
#
# ¿Qué es SQLite? Una base de datos que vive en UN solo archivo
# (datos/mercado.db). Guarda la información en "tablas", parecidas a una
# hoja de Excel: cada fila es un registro y cada columna un dato.
# Se le habla con un lenguaje llamado SQL ("CREATE TABLE", "SELECT"...).
# Python trae SQLite incluido (módulo "sqlite3"), no hay que instalar nada.

import sqlite3

# "pandas" es la librería más usada en Python para trabajar con tablas de
# datos. Su tipo principal es el "DataFrame": una tabla con filas y columnas.
import pandas as pd

import config


# Instrucciones SQL para crear las tablas si todavía no existen.
# El texto entre triples comillas """ puede ocupar varias líneas.
ESQUEMA = """
-- Una fila por activo y día de bolsa.
CREATE TABLE IF NOT EXISTS diario (
    ticker   TEXT NOT NULL,   -- código del activo, p. ej. 'SPY'
    fecha    TEXT NOT NULL,   -- día, formato 'AAAA-MM-DD'
    apertura REAL,            -- precio al abrir el mercado
    maximo   REAL,            -- precio más alto del día
    minimo   REAL,            -- precio más bajo del día
    cierre   REAL,            -- precio al cerrar el mercado
    volumen  REAL,            -- cantidad negociada
    -- La "clave primaria" impide tener dos filas del mismo activo y día.
    PRIMARY KEY (ticker, fecha)
);

-- Una fila por activo y vela de pocos minutos (hora de Nueva York).
CREATE TABLE IF NOT EXISTS intradia (
    ticker     TEXT NOT NULL,
    fecha_hora TEXT NOT NULL, -- 'AAAA-MM-DD HH:MM' en hora de Nueva York
    apertura   REAL,
    maximo     REAL,
    minimo     REAL,
    cierre     REAL,
    volumen    REAL,
    PRIMARY KEY (ticker, fecha_hora)
);

-- Pequeña tabla de notas: p. ej. si los datos son reales o simulados.
CREATE TABLE IF NOT EXISTS metadatos (
    clave TEXT PRIMARY KEY,
    valor TEXT
);
"""

# Columnas de precio, en el orden en que las guardamos.
COLUMNAS_PRECIO = ["apertura", "maximo", "minimo", "cierre", "volumen"]


def conectar():
    # Abre (o crea, si no existe) el archivo de la base de datos y se
    # asegura de que las tablas existen. Devuelve la "conexión", el objeto
    # con el que luego enviamos órdenes SQL.
    config.CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(config.BASE_DATOS)
    conexion.executescript(ESQUEMA)
    return conexion


def guardar_precios(tabla, ticker, df):
    # Guarda en "tabla" ('diario' o 'intradia') las filas de "df", un
    # DataFrame con las columnas fecha (o fecha_hora) + COLUMNAS_PRECIO.
    #
    # Usamos "INSERT OR REPLACE": si la fila (ticker + fecha) ya existe, se
    # sustituye; si no, se añade. Así podemos ejecutar la descarga muchas
    # veces sin duplicar datos, y las velas intradía se van ACUMULANDO
    # aunque Yahoo solo nos dé los últimos 60 días cada vez.
    columna_tiempo = "fecha" if tabla == "diario" else "fecha_hora"

    # Convertimos la tabla de pandas en una lista de tuplas (filas) para SQL.
    filas = [
        (ticker, fila[columna_tiempo], *[fila[c] for c in COLUMNAS_PRECIO])
        for _, fila in df.iterrows()
    ]

    # Los "?" son huecos que sqlite3 rellena con cada fila de forma segura.
    sql = (
        f"INSERT OR REPLACE INTO {tabla} "
        f"(ticker, {columna_tiempo}, {', '.join(COLUMNAS_PRECIO)}) "
        f"VALUES (?, ?, ?, ?, ?, ?, ?)"
    )

    # "with" abre la conexión y la cierra (guardando los cambios) al terminar.
    with conectar() as conexion:
        conexion.executemany(sql, filas)
    return len(filas)


def borrar_fuera_de_horario():
    # Borra velas intradía guardadas fuera del horario normal (9:30-15:55,
    # hora de Nueva York). substr(fecha_hora, 12, 5) recorta la parte
    # "HH:MM" del texto 'AAAA-MM-DD HH:MM'. Devuelve cuántas filas borró.
    with conectar() as conexion:
        cursor = conexion.execute(
            "DELETE FROM intradia "
            "WHERE substr(fecha_hora, 12, 5) < '09:30' "
            "   OR substr(fecha_hora, 12, 5) > '15:55'"
        )
    return cursor.rowcount


def borrar_filas_sin_precio():
    # Borra filas guardadas con el precio de apertura o de cierre vacío
    # (NULL en SQL). Devuelve cuántas filas borró en total.
    total = 0
    with conectar() as conexion:
        for tabla in ["diario", "intradia"]:
            cursor = conexion.execute(
                f"DELETE FROM {tabla} WHERE apertura IS NULL OR cierre IS NULL")
            total += cursor.rowcount
    return total


def guardar_metadato(clave, valor):
    # Apunta una nota en la tabla "metadatos" (p. ej. origen = 'yahoo').
    with conectar() as conexion:
        conexion.execute(
            "INSERT OR REPLACE INTO metadatos (clave, valor) VALUES (?, ?)",
            (clave, valor),
        )


def leer_metadato(clave, por_defecto=None):
    # Lee una nota de la tabla "metadatos". Si no existe, devuelve "por_defecto".
    with conectar() as conexion:
        fila = conexion.execute(
            "SELECT valor FROM metadatos WHERE clave = ?", (clave,)
        ).fetchone()
    return fila[0] if fila else por_defecto


def leer_diario(ticker):
    # Devuelve el histórico diario de un ticker como DataFrame, con la fecha
    # como índice (la "columna de etiquetas" de las filas), ordenado en el tiempo.
    with conectar() as conexion:
        df = pd.read_sql_query(
            "SELECT * FROM diario WHERE ticker = ? ORDER BY fecha",
            conexion,
            params=(ticker,),
        )
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df.set_index("fecha")


def leer_cierres_diarios(tickers):
    # Devuelve UNA tabla con el precio de cierre de varios tickers:
    # una columna por ticker y una fila por día. Muy práctica para
    # comparar activos y calcular correlaciones.
    columnas = {t: leer_diario(t)["cierre"] for t in tickers}
    # pd.DataFrame(diccionario) alinea las fechas automáticamente.
    return pd.DataFrame(columnas)


def leer_intradia(ticker):
    # Igual que leer_diario, pero con las velas de pocos minutos.
    with conectar() as conexion:
        df = pd.read_sql_query(
            "SELECT * FROM intradia WHERE ticker = ? ORDER BY fecha_hora",
            conexion,
            params=(ticker,),
        )
    df["fecha_hora"] = pd.to_datetime(df["fecha_hora"])
    return df.set_index("fecha_hora")


def exportar_csv():
    # Copia cada tabla de precios a archivos CSV (uno por ticker y tabla),
    # para poder mirarlos en Excel o en GitHub desde el móvil.
    config.CARPETA_CSV.mkdir(parents=True, exist_ok=True)
    for ticker in config.TODOS:
        # El "^" no queda bien en nombres de archivo: lo quitamos.
        nombre = ticker.replace("^", "")
        leer_diario(ticker).to_csv(config.CARPETA_CSV / f"{nombre}_diario.csv")
        leer_intradia(ticker).to_csv(config.CARPETA_CSV / f"{nombre}_intradia.csv")
