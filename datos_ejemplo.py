# datos_ejemplo.py
# Genera precios INVENTADOS con el mismo formato que descargar_datos.py,
# para poder probar los gráficos sin conexión a Yahoo Finance.
# (Es la misma idea que datos_ejemplo.py del repo de backtesting de BTC.)
#
# Cómo se usa:   python datos_ejemplo.py
#
# ⚠️ Los precios son ALEATORIOS. No saques ninguna conclusión de inversión
# con ellos. Los gráficos mostrarán un aviso grande mientras sean simulados.

import numpy as np  # "numpy": cálculos rápidos con listas de números
import pandas as pd

import almacen
import config


# "Semilla" del generador aleatorio: con la misma semilla salen siempre
# los mismos números, así los resultados se pueden repetir.
generador = np.random.default_rng(42)


def simular_diario():
    # Días hábiles (lunes a viernes) desde 2007 hasta hoy.
    fechas = pd.bdate_range(config.INICIO_DIARIO, pd.Timestamp.today().normalize())
    n = len(fechas)

    # VIX: oscila alrededor de 19 y vuelve hacia esa media (como el real),
    # con algún "susto" repentino de vez en cuando.
    vix = np.empty(n)
    vix[0] = 15.0
    for i in range(1, n):
        susto = 15 if generador.random() < 0.002 else 0  # muy de vez en cuando
        vix[i] = vix[i - 1] + 0.03 * (19 - vix[i - 1]) + generador.normal(0, 1.2) + susto
        vix[i] = max(vix[i], 9)  # el VIX real casi nunca baja de ~9

    # S&P 500: cuando el VIX SUBE, la bolsa suele BAJAR (y al revés).
    # Por eso restamos una parte del cambio del VIX al rendimiento diario.
    cambio_vix = np.diff(vix, prepend=vix[0])
    volatilidad = vix / 100 / np.sqrt(252)  # VIX anual → volatilidad diaria
    rend_sp = 0.0003 - 0.004 * cambio_vix + generador.normal(0, 1, n) * volatilidad * 0.5
    sp = 1400 * np.cumprod(1 + rend_sp)  # cumprod = ir multiplicando día a día

    # El resto de índices se parecen al S&P con algo de ruido propio.
    nasdaq = 2400 * np.cumprod(1 + rend_sp * 1.2 + generador.normal(0, 0.004, n))
    dow = 12400 * np.cumprod(1 + rend_sp * 0.9 + generador.normal(0, 0.003, n))

    # Cada ETF es (aprox.) su índice dividido por un número fijo.
    series = {
        "^VIX": vix, "^GSPC": sp, "^IXIC": nasdaq, "^DJI": dow,
        "SPY": sp / 10, "QQQ": nasdaq / 55, "DIA": dow / 100,
    }
    return fechas, series


def a_tabla(tiempos, cierres, formato):
    # Construye apertura/máximo/mínimo alrededor del cierre para que la
    # tabla tenga todas las columnas, igual que los datos reales.
    apertura = np.roll(cierres, 1)
    apertura[0] = cierres[0]
    ruido = np.abs(generador.normal(0, 0.003, len(cierres)))
    return pd.DataFrame({
        "t": tiempos.strftime(formato),
        "apertura": apertura,
        "maximo": np.maximum(apertura, cierres) * (1 + ruido),
        "minimo": np.minimum(apertura, cierres) * (1 - ruido),
        "cierre": cierres,
        "volumen": generador.integers(1_000_000, 5_000_000, len(cierres)).astype(float),
    })


def simular_intradia(ultimo_cierre):
    # Velas de 5 minutos de los últimos 5 días hábiles, de 9:30 a 15:55
    # (la última vela empieza a las 15:55 y termina a las 16:00).
    dias = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=5)
    horas = pd.DatetimeIndex([
        d + pd.Timedelta(hours=9, minutes=30) + pd.Timedelta(minutes=5 * k)
        for d in dias for k in range(78)  # 78 velas × 5 min = 6,5 horas
    ])
    pasos = 1 + generador.normal(0, 0.0008, len(horas))
    return horas, ultimo_cierre * np.cumprod(pasos)


if __name__ == "__main__":
    fechas, series = simular_diario()
    for ticker, cierres in series.items():
        diario = a_tabla(fechas, cierres, "%Y-%m-%d").rename(columns={"t": "fecha"})
        almacen.guardar_precios("diario", ticker, diario)

        horas, cierres_5m = simular_intradia(cierres[-1])
        intradia = a_tabla(horas, cierres_5m, "%Y-%m-%d %H:%M").rename(columns={"t": "fecha_hora"})
        almacen.guardar_precios("intradia", ticker, intradia)
        print(f"{ticker}: {len(diario)} días + {len(intradia)} velas de 5 min (SIMULADOS)")

    # Marcamos la base de datos como simulada para que nadie se confunda.
    almacen.guardar_metadato("origen", "SIMULADO")
    almacen.guardar_metadato("actualizado", pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"))
    almacen.exportar_csv()
    print(f"\n⚠️  Datos INVENTADOS guardados en {config.BASE_DATOS}")
    print("   Para datos reales ejecuta: python descargar_datos.py")
