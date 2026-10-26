# indicadores.py
# FASE 2, paso 1: los "ingredientes" de las señales.
#   - Régimen del VIX: calma / normal / nervioso / pánico.
#   - Medias móviles de 50 y 200 días: la tendencia del precio.
#   - RSI de 14 días: si el precio ha subido o bajado "demasiado deprisa".
#
# Todas las funciones reciben una serie de precios de pandas (una columna
# con una fecha por fila) y devuelven otra serie del mismo tamaño.
#
# ⚠️ Regla de oro contra el "look-ahead bias" (mirar el futuro sin querer):
# cada valor del día D se calcula SOLO con precios del día D y anteriores.
# Las funciones de pandas que usamos (.rolling, .ewm) ya funcionan así.

import pandas as pd


# ---------------------------------------------------------------------------
# PARÁMETROS (en Fase 3 veremos por qué NO conviene "afinarlos" a ojo)
# ---------------------------------------------------------------------------

MEDIA_CORTA = 50    # días de bolsa (~2,5 meses)
MEDIA_LARGA = 200   # días de bolsa (~10 meses)
PERIODO_RSI = 14    # el valor clásico que propuso su inventor, J. Welles Wilder

RSI_SOBRECOMPRA = 70  # por encima: ha subido muy deprisa
RSI_SOBREVENTA = 30   # por debajo: ha bajado muy deprisa

# Límites del VIX que pediste: (nombre, desde, hasta).
REGIMENES_VIX = [
    ("calma", 0, 15),
    ("normal", 15, 20),
    ("nervioso", 20, 30),
    ("pánico", 30, float("inf")),  # float("inf") = infinito
]


def regimen_vix(valor_vix, ajuste=0):
    # Devuelve el nombre del régimen para UN valor del VIX.
    # "ajuste" mueve todos los límites (15, 20, 30) a la vez: con ajuste=2
    # serían 17, 22 y 32. Solo se usa para probar la robustez (Fase 3b).
    for nombre, desde, hasta in REGIMENES_VIX:
        if desde > 0:
            desde += ajuste
        hasta += ajuste
        if desde <= valor_vix < hasta:
            return nombre
    return None  # p. ej. si el valor falta (NaN)


def media_movil(precios, dias):
    # Media de los últimos "dias" cierres, recalculada cada día.
    # Los primeros (dias - 1) días no tienen suficiente historia → NaN
    # ("Not a Number", el valor vacío de pandas).
    return precios.rolling(dias).mean()


def rsi(precios, periodo=PERIODO_RSI):
    # RSI (Relative Strength Index, "índice de fuerza relativa"), de 0 a 100.
    #
    # Idea: compara cuánto ha subido el precio en los días buenos con cuánto
    # ha bajado en los días malos, en las últimas ~14 sesiones.
    #   RSI cerca de 100 → casi todo han sido subidas (sobrecompra).
    #   RSI cerca de 0   → casi todo han sido bajadas (sobreventa).
    cambios = precios.diff()                 # precio de hoy - precio de ayer
    subidas = cambios.clip(lower=0)          # deja solo los cambios positivos
    bajadas = -cambios.clip(upper=0)         # deja solo los negativos (en positivo)

    # Media "suavizada" de Wilder: da más peso a los días recientes.
    # alpha = 1/14 significa que cada día nuevo cuenta 1/14 en la media.
    media_subidas = subidas.ewm(alpha=1 / periodo, min_periods=periodo, adjust=False).mean()
    media_bajadas = bajadas.ewm(alpha=1 / periodo, min_periods=periodo, adjust=False).mean()

    fuerza = media_subidas / media_bajadas   # "RS" en la fórmula original
    return 100 - 100 / (1 + fuerza)


def calcular_indicadores(precio, vix, corta=MEDIA_CORTA, larga=MEDIA_LARGA, ajuste_vix=0):
    # Junta todos los indicadores en una sola tabla (DataFrame).
    # "precio" y "vix" son series de cierres diarios. Los demás parámetros
    # tienen valores por defecto; solo se cambian para probar la robustez.
    tabla = pd.DataFrame({"precio": precio, "vix": vix}).dropna()
    tabla["media_corta"] = media_movil(tabla["precio"], corta)
    tabla["media_larga"] = media_movil(tabla["precio"], larga)
    tabla["rsi"] = rsi(tabla["precio"])
    # .map() aplica la función a cada valor de la columna.
    tabla["regimen"] = tabla["vix"].map(lambda v: regimen_vix(v, ajuste_vix))
    return tabla
