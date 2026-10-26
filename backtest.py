# backtest.py
# FASE 3, paso 1: el MOTOR del backtest.
# Simula día a día qué habría pasado con 10.000 USD ficticios invertidos en
# el ETF SPY siguiendo una estrategia, con comisiones y deslizamiento.
#
# Estrategias que comparamos:
#   1) "Estrategia completa": las señales de la Fase 2 (tendencia + VIX + RSI).
#   2) "Solo VIX": solo mira el régimen del VIX.
#   3) "Comprar y mantener SPY": comprar el primer día y no vender nunca.
#      Es la referencia que hay que superar.
#
# REGLAS PARA SER HONESTOS (evitar el "look-ahead bias"):
#   - La señal de un día se calcula con el precio de CIERRE de ese día.
#   - Por eso la orden se ejecuta al día SIGUIENTE, al precio de APERTURA.
#     Nunca usamos un precio que no se conocía en el momento de decidir.
#   - Cada compra paga un precio un poco peor (deslizamiento) y una comisión.
#   - El dinero que no está invertido no gana intereses (supuesto prudente).

import math

import pandas as pd

import almacen
import senales


# ---------------------------------------------------------------------------
# PARÁMETROS DE LA SIMULACIÓN
# ---------------------------------------------------------------------------

CAPITAL_INICIAL = 10_000  # USD ficticios

# Comisión: % del valor de cada compra o venta. 0,05 % = 5 USD por cada 10.000.
COMISION = 0.0005

# Deslizamiento ("slippage"): el precio al que de verdad compras suele ser un
# poco peor que el que ves en pantalla. Simulamos que compramos un 0,05 % más
# caro y vendemos un 0,05 % más barato.
DESLIZAMIENTO = 0.0005

# Separación entrenamiento / prueba (ver explicación en la página):
#   entrenamiento: desde el inicio hasta el 31/12/2016
#   prueba:        desde el 01/01/2017 hasta hoy
INICIO_PRUEBA = "2017-01-01"

# Periodos de crisis que nos interesan: (desde, hasta).
CRISIS = {
    "Crisis financiera 2008": ("2007-10-01", "2009-06-30"),
    "COVID 2020": ("2020-01-01", "2020-12-31"),
    "Bajista 2022": ("2022-01-01", "2022-12-31"),
}


# ---------------------------------------------------------------------------
# ESTRATEGIAS
# Cada estrategia devuelve, para cada día, la "posición deseada":
#   1   = estar invertido al 100 % en SPY
#   0   = estar fuera (todo en efectivo)
#   NaN = no cambiar nada (MANTENER lo que haya)
# ---------------------------------------------------------------------------

def estrategia_completa(tabla):
    # Las señales de la Fase 2: COMPRAR → dentro, REDUCIR → fuera,
    # MANTENER → sin cambios. ("Reducir" lo simulamos como salir del todo.)
    traduccion = {"COMPRAR": 1, "REDUCIR": 0, "MANTENER": float("nan"), "SIN DATOS": 0}
    return tabla["senal"].map(traduccion)


def estrategia_solo_vix(tabla, umbral_entrada=20, umbral_salida=30):
    # Solo mira el VIX (por defecto, los mismos límites de los regímenes):
    #   VIX < 20 (calma o normal) → dentro
    #   VIX ≥ 30 (pánico)         → fuera
    #   entre 20 y 30 (nervioso)  → sin cambios
    # Así, tras un pánico no se vuelve a entrar hasta que el VIX baja de 20.
    vix = tabla["vix"]
    posicion = pd.Series(float("nan"), index=tabla.index)
    posicion[vix < umbral_entrada] = 1
    posicion[vix >= umbral_salida] = 0
    return posicion


def comprar_y_mantener(tabla):
    # Siempre dentro: compra el primer día y no vende nunca.
    return pd.Series(1, index=tabla.index)


# ---------------------------------------------------------------------------
# EL MOTOR
# ---------------------------------------------------------------------------

def preparar_datos(**parametros):
    # Junta en una tabla: señales (calculadas sobre el S&P 500 y el VIX) y
    # precios de apertura y cierre de SPY (ajustados por dividendos).
    # "parametros" (opcional) se pasa a calcular_senales para probar variantes.
    tabla = senales.calcular_senales(**parametros)
    spy = almacen.leer_diario("SPY")[["apertura", "cierre"]]
    tabla = tabla.join(spy, how="inner")
    # Empezamos el primer día con señal (antes faltan 200 días de historia).
    primer_dia = tabla.index[(tabla["senal"] != "SIN DATOS").argmax()]
    return tabla.loc[primer_dia:]


def simular(tabla, posicion_deseada, inicio=None, fin=None, ejecutar_mismo_dia=False):
    # Recorre los días uno a uno y devuelve un diccionario con:
    #   "valor":       valor de la cartera al cierre de cada día (USD)
    #   "invertido":   True/False, si ese día se tenían acciones
    #   "operaciones": lista de operaciones (compra + venta)
    #   "costes":      total pagado en comisiones y deslizamiento
    #
    # ejecutar_mismo_dia=True es la versión TRAMPOSA: ejecuta al cierre del
    # mismo día que da la señal. Solo la usamos para enseñar el look-ahead bias.
    datos = tabla.loc[inicio:fin]
    deseada = posicion_deseada.loc[datos.index]

    efectivo = CAPITAL_INICIAL
    acciones = 0
    costes = 0.0
    operaciones = []
    abierta = None      # la operación en curso (si estamos dentro)
    pendiente = None    # orden decidida ayer, a ejecutar hoy en la apertura
    valores, invertido = [], []

    def ejecutar(objetivo, precio, fecha):
        # Compra o vende TODO para llegar a la posición objetivo (0 o 1).
        # "nonlocal" permite modificar variables de la función de fuera.
        nonlocal efectivo, acciones, costes, abierta
        if objetivo == 1 and acciones == 0:
            precio_real = precio * (1 + DESLIZAMIENTO)
            # Cuántas acciones enteras podemos pagar, comisión incluida.
            # math.floor redondea hacia abajo (no se compran trozos).
            n = math.floor(efectivo / (precio_real * (1 + COMISION)))
            if n == 0:
                return
            importe = n * precio_real
            comision = importe * COMISION
            efectivo -= importe + comision
            acciones = n
            costes += comision + n * (precio_real - precio)
            abierta = {"entrada": fecha, "precio_entrada": precio_real,
                       "coste_entrada": importe + comision, "acciones": n}
        elif objetivo == 0 and acciones > 0:
            precio_real = precio * (1 - DESLIZAMIENTO)
            importe = acciones * precio_real
            comision = importe * COMISION
            efectivo += importe - comision
            costes += comision + acciones * (precio - precio_real)
            abierta.update({"salida": fecha, "precio_salida": precio_real,
                            "resultado": (importe - comision) / abierta["coste_entrada"] - 1})
            operaciones.append(abierta)
            acciones, abierta = 0, None

    for fecha, fila in datos.iterrows():
        # 1) Por la mañana: ejecutar la orden que se decidió ayer.
        if pendiente is not None:
            ejecutar(pendiente, fila.apertura, fecha)
            pendiente = None

        # 2) Al cierre: mirar la señal de hoy y decidir.
        objetivo = deseada.loc[fecha]
        if not pd.isna(objetivo):
            if ejecutar_mismo_dia:
                ejecutar(objetivo, fila.cierre, fecha)  # ⚠️ trampa: usa el cierre de hoy
            else:
                pendiente = objetivo                    # ✅ honesto: mañana en la apertura

        # 3) Apuntar cuánto vale la cartera al cierre.
        valores.append(efectivo + acciones * fila.cierre)
        invertido.append(acciones > 0)

    # Si al final seguimos dentro, apuntamos la operación como "abierta",
    # valorada al último cierre (sin costes de venta, porque no se vendió).
    if abierta is not None:
        ultimo = datos.index[-1]
        valor_actual = acciones * datos["cierre"].iloc[-1]
        abierta.update({"salida": ultimo, "precio_salida": datos["cierre"].iloc[-1],
                        "resultado": valor_actual / abierta["coste_entrada"] - 1,
                        "sigue_abierta": True})
        operaciones.append(abierta)

    return {
        "valor": pd.Series(valores, index=datos.index),
        "invertido": pd.Series(invertido, index=datos.index),
        "operaciones": operaciones,
        "costes": costes,
    }


# ---------------------------------------------------------------------------
# MÉTRICAS
# ---------------------------------------------------------------------------

def caida_maxima(valor):
    # Máxima caída ("drawdown"): la peor bajada desde un máximo anterior.
    # .cummax() = el máximo alcanzado hasta cada día.
    caidas = valor / valor.cummax() - 1
    valle = caidas.idxmin()                 # el día del peor momento
    pico = valor.loc[:valle].idxmax()       # el máximo anterior a ese día
    return caidas.min(), pico, valle


def metricas(resultado):
    valor = resultado["valor"]
    rendimientos = valor.pct_change().dropna()   # % que gana o pierde cada día
    anos = (valor.index[-1] - valor.index[0]).days / 365.25
    total = valor.iloc[-1] / CAPITAL_INICIAL - 1
    caida, pico, valle = caida_maxima(valor)
    cerradas = [o for o in resultado["operaciones"] if not o.get("sigue_abierta")]
    return {
        "valor_final": valor.iloc[-1],
        "retorno_total": total,
        # Retorno anual compuesto: el % fijo por año que da el mismo total.
        "retorno_anual": (1 + total) ** (1 / anos) - 1,
        "caida_maxima": caida,
        "pico": pico,
        "valle": valle,
        # Sharpe: rendimiento medio / variabilidad, pasado a escala anual
        # (√252 días de bolsa). Más alto = más rendimiento por cada susto.
        # Lo calculamos sin restar el tipo de interés sin riesgo (supuesto simple).
        "sharpe": rendimientos.mean() / rendimientos.std() * math.sqrt(252),
        "operaciones": len(resultado["operaciones"]),
        "ganadoras": (sum(o["resultado"] > 0 for o in cerradas) / len(cerradas)) if cerradas else None,
        "tiempo_invertido": resultado["invertido"].mean(),
        "costes": resultado["costes"],
    }


def caida_en_periodo(valor, desde, hasta):
    # Máxima caída y retorno DENTRO de un periodo (p. ej. la crisis de 2008),
    # medidos sobre la misma simulación continua.
    tramo = valor.loc[desde:hasta]
    caida = (tramo / tramo.cummax() - 1).min()
    return caida, tramo.iloc[-1] / tramo.iloc[0] - 1


# ---------------------------------------------------------------------------
# EJECUCIÓN DE TODAS LAS PRUEBAS
# ---------------------------------------------------------------------------

ESTRATEGIAS = {
    "Estrategia completa": estrategia_completa,
    "Solo VIX": estrategia_solo_vix,
    "Comprar y mantener SPY": comprar_y_mantener,
}


def ejecutar_todo():
    tabla = preparar_datos()
    resultados = {}

    for nombre, funcion in ESTRATEGIAS.items():
        posicion = funcion(tabla)
        completo = simular(tabla, posicion)
        resultados[nombre] = {
            "completo": completo,
            "metricas": metricas(completo),
            # Entrenamiento y prueba: dos simulaciones separadas, cada una
            # empezando con 10.000 USD.
            "entrenamiento": metricas(simular(tabla, posicion, fin="2016-12-31")),
            "prueba": metricas(simular(tabla, posicion, inicio=INICIO_PRUEBA)),
            "crisis": {c: caida_en_periodo(completo["valor"], *f) for c, f in CRISIS.items()},
        }

    return tabla, resultados


def demo_look_ahead(tabla):
    # La misma estrategia completa, ejecutada de forma honesta (apertura del
    # día siguiente) y de forma tramposa (cierre del mismo día de la señal).
    posicion = estrategia_completa(tabla)
    honesta = metricas(simular(tabla, posicion))
    tramposa = metricas(simular(tabla, posicion, ejecutar_mismo_dia=True))
    return honesta, tramposa


def demo_sobreajuste(tabla):
    # Probamos muchas combinaciones de umbrales del VIX SOLO con los datos de
    # entrenamiento, elegimos la que mejor Sharpe dio, y luego miramos cómo le
    # va en los datos de prueba, que no ha "visto". Si cae mucho, era suerte.
    # (Aquí calculamos también la prueba de TODAS solo para poder enseñar
    # el ranking; en la vida real la prueba se mira una única vez, al final.)
    filas = []
    for entrada in [15, 17.5, 20, 22.5, 25]:
        for salida in [25, 30, 35, 40, 45]:
            if entrada >= salida:
                continue
            posicion = estrategia_solo_vix(tabla, entrada, salida)
            entreno = metricas(simular(tabla, posicion, fin="2016-12-31"))
            prueba = metricas(simular(tabla, posicion, inicio=INICIO_PRUEBA))
            filas.append({"entrada": entrada, "salida": salida,
                          "sharpe_entrenamiento": entreno["sharpe"],
                          "anual_entrenamiento": entreno["retorno_anual"],
                          "sharpe_prueba": prueba["sharpe"],
                          "anual_prueba": prueba["retorno_anual"],
                          "caida_prueba": prueba["caida_maxima"]})

    ranking = pd.DataFrame(filas)
    # Puesto de cada combinación (1 = mejor Sharpe) en cada periodo.
    ranking["puesto_entrenamiento"] = ranking["sharpe_entrenamiento"].rank(ascending=False).astype(int)
    ranking["puesto_prueba"] = ranking["sharpe_prueba"].rank(ascending=False).astype(int)
    return ranking.sort_values("puesto_entrenamiento")


if __name__ == "__main__":
    tabla, resultados = ejecutar_todo()
    print(f"Periodo: {tabla.index[0]:%d/%m/%Y} → {tabla.index[-1]:%d/%m/%Y}\n")
    for nombre, r in resultados.items():
        m = r["metricas"]
        print(f"{nombre}:")
        print(f"  {CAPITAL_INICIAL:,} USD → {m['valor_final']:,.0f} USD "
              f"({m['retorno_total']:+.0%}, {m['retorno_anual']:+.1%} al año)")
        print(f"  máxima caída {m['caida_maxima']:.1%} ({m['pico']:%d/%m/%Y} → {m['valle']:%d/%m/%Y}), "
              f"Sharpe {m['sharpe']:.2f}, {m['operaciones']} operaciones")
        for crisis, (caida, ret) in r["crisis"].items():
            print(f"    {crisis}: caída máx {caida:.1%}, retorno {ret:+.1%}")
