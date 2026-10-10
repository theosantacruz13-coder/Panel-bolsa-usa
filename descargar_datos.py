# descargar_datos.py
# FASE 1, paso 1: descargar precios REALES de Yahoo Finance (gratis, sin
# login, solo lectura) y guardarlos en la base de datos SQLite + CSV.
#
# Cómo se usa:   python descargar_datos.py
#
# Descarga dos cosas para cada activo de config.py:
#   1) Histórico DIARIO desde 2007 (una vela por día de bolsa).
#   2) Velas INTRADÍA de 5 minutos de los últimos ~60 días (es lo máximo
#      que Yahoo da gratis). Como guardamos con "INSERT OR REPLACE", si
#      ejecutas este script cada pocos días, la base de datos va
#      acumulando más y más historia intradía.

# "time" nos deja hacer pausas para no saturar a Yahoo con peticiones.
import time

# "yfinance" es una librería gratuita que lee los precios públicos de
# Yahoo Finance. NO es un bróker: no puede comprar ni vender nada.
import yfinance as yf

import almacen
import config


# Cuántas veces reintentamos si una descarga falla (internet inestable...).
REINTENTOS = 3


def descargar_con_reintentos(ticker, **parametros):
    # Pide datos a Yahoo y, si falla o llegan vacíos, lo vuelve a intentar.
    # "**parametros" recoge cualquier argumento con nombre (start=..., interval=...)
    # y se lo pasa tal cual a yfinance.
    for intento in range(1, REINTENTOS + 1):
        try:
            # .history() devuelve un DataFrame con columnas Open, High, Low,
            # Close, Volume... y la fecha como índice.
            # auto_adjust=True: los precios de los ETF se ajustan por los
            # dividendos que reparten (así "comprar y mantener" es justo).
            df = yf.Ticker(ticker).history(auto_adjust=True, **parametros)
            if not df.empty:
                return df
            print(f"   {ticker}: Yahoo devolvió 0 filas (intento {intento})")
        except Exception as error:
            # "except" atrapa el error para que el programa no se detenga.
            print(f"   {ticker}: error '{error}' (intento {intento})")
        # Esperamos un poco más en cada intento: 2 s, 4 s, 6 s...
        time.sleep(2 * intento)
    # Si llegamos aquí, todos los intentos fallaron.
    return None


def a_formato_nuestro(df, formato_fecha, columna_tiempo):
    # Yahoo usa nombres en inglés; los pasamos a los nuestros en español
    # y convertimos la fecha en texto (SQLite guarda las fechas como texto).
    df = df.rename(columns={
        "Open": "apertura",
        "High": "maximo",
        "Low": "minimo",
        "Close": "cierre",
        "Volume": "volumen",
    })
    # Las velas intradía las pasamos a la hora de Nueva York, que es donde
    # cotiza la bolsa (abre a las 9:30 y cierra a las 16:00, hora local).
    if columna_tiempo == "fecha_hora":
        df.index = df.index.tz_convert("America/New_York")
    df[columna_tiempo] = df.index.strftime(formato_fecha)
    return df[[columna_tiempo] + almacen.COLUMNAS_PRECIO]


def descargar_todo():
    # Recorre todos los tickers y descarga diario + intradía.
    # Devuelve una lista con los tickers que fallaron (vacía si todo fue bien).
    fallidos = []

    # .items() da pares (clave, valor) del diccionario.
    for ticker, descripcion in config.TODOS.items():
        print(f"\n{ticker} – {descripcion}")

        # 1) Histórico diario.
        diario = descargar_con_reintentos(
            ticker, start=config.INICIO_DIARIO, interval="1d"
        )
        if diario is None:
            fallidos.append(ticker)
            continue  # "continue" salta al siguiente ticker del bucle
        diario = a_formato_nuestro(diario, "%Y-%m-%d", "fecha")
        n = almacen.guardar_precios("diario", ticker, diario)
        print(f"   diario:   {n} días ({diario['fecha'].iloc[0]} → {diario['fecha'].iloc[-1]})")

        # 2) Velas de 5 minutos (solo horario normal de mercado, sin
        #    pre-apertura ni after-hours: prepost=False).
        intradia = descargar_con_reintentos(
            ticker,
            period=config.PERIODO_INTRADIA,
            interval=config.INTERVALO_INTRADIA,
            prepost=False,
        )
        if intradia is None:
            print("   intradía: no disponible ahora mismo (seguimos con el resto)")
        else:
            intradia = a_formato_nuestro(intradia, "%Y-%m-%d %H:%M", "fecha_hora")
            n = almacen.guardar_precios("intradia", ticker, intradia)
            print(f"   intradía: {n} velas de 5 min")

        # Pausa cortita entre activos para ser amables con el servidor.
        time.sleep(1)

    return fallidos


# Este bloque solo se ejecuta si lanzas el archivo directamente
# ("python descargar_datos.py"), no cuando otro script lo importa.
if __name__ == "__main__":
    print("Descargando datos de Yahoo Finance...")
    fallidos = descargar_todo()

    # Anotamos que estos datos son reales (explorar.py lo comprueba).
    if len(fallidos) < len(config.TODOS):
        almacen.guardar_metadato("origen", "yahoo")
        almacen.guardar_metadato("actualizado", time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()))
        almacen.exportar_csv()

    print(f"\nBase de datos: {config.BASE_DATOS}")
    print(f"CSV:           {config.CARPETA_CSV}/")
    if fallidos:
        print(f"⚠️  No se pudo descargar: {', '.join(fallidos)}")
        # Código de salida 1 = "algo fue mal" (lo ve GitHub Actions).
        raise SystemExit(1)
    print("✅ Todo descargado.")
