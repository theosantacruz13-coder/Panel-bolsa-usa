# config.py
# Configuración común a todo el proyecto. Los demás scripts hacen
# "import config" y leen estos valores, así solo hay que cambiarlos aquí.
# Por convención, en Python las constantes se escriben en MAYÚSCULAS.

# "pathlib" sirve para trabajar con rutas de carpetas y archivos de forma
# segura en cualquier sistema operativo (Windows, Mac, Linux).
from pathlib import Path


# ---------------------------------------------------------------------------
# ACTIVOS QUE SEGUIMOS
# Un "ticker" es el código corto con el que se identifica un activo en bolsa.
# En Yahoo Finance los índices empiezan por "^" (no se pueden comprar
# directamente; son solo un número que resume un grupo de acciones).
# ---------------------------------------------------------------------------

# Diccionario "ticker: descripción". Las llaves {} crean un diccionario.
INDICES = {
    "^VIX": "VIX (índice del miedo: volatilidad esperada del S&P 500)",
    "^GSPC": "S&P 500 (las 500 mayores empresas de EE.UU.)",
    "^DJI": "Dow Jones (30 grandes empresas industriales)",
    "^IXIC": "Nasdaq Composite (muchas tecnológicas)",
}

# Los ETF sí se pueden comprar como si fueran una acción. Cada uno copia
# ("sigue") a un índice. Son los que usaremos para simular inversiones.
ETFS = {
    "SPY": "ETF que sigue al S&P 500",
    "QQQ": "ETF que sigue al Nasdaq-100 (las 100 mayores del Nasdaq)",
    "DIA": "ETF que sigue al Dow Jones",
}

# Todos los tickers juntos. "|" une dos diccionarios en uno.
TODOS = INDICES | ETFS

# Nombres cortos para títulos de gráficos.
NOMBRE_CORTO = {
    "^VIX": "VIX",
    "^GSPC": "S&P 500",
    "^DJI": "Dow Jones",
    "^IXIC": "Nasdaq",
    "SPY": "SPY",
    "QQQ": "QQQ",
    "DIA": "DIA",
}


# ---------------------------------------------------------------------------
# CUÁNTOS DATOS DESCARGAMOS
# ---------------------------------------------------------------------------

# Fecha desde la que pedimos el histórico diario (más de 10 años).
# Empezar en 2007 incluye la crisis de 2008, el COVID de 2020 y la caída
# de 2022: periodos de "pánico" muy útiles para probar estrategias.
INICIO_DIARIO = "2007-01-01"

# Velas intradía: cada cuántos minutos. Yahoo solo guarda las velas de
# 5 minutos de los últimos ~60 días, por eso las iremos acumulando
# en nuestra base de datos cada vez que ejecutemos la descarga.
INTERVALO_INTRADIA = "5m"
PERIODO_INTRADIA = "60d"


# ---------------------------------------------------------------------------
# DÓNDE GUARDAMOS LAS COSAS
# ---------------------------------------------------------------------------

# Path(__file__) es la ruta de este mismo archivo; .parent es su carpeta.
CARPETA_PROYECTO = Path(__file__).parent

# Carpeta con los datos descargados.
CARPETA_DATOS = CARPETA_PROYECTO / "datos"

# Base de datos SQLite: un único archivo que funciona como una pequeña
# base de datos con tablas, sin instalar ningún servidor.
BASE_DATOS = CARPETA_DATOS / "mercado.db"

# Copias en CSV (se pueden abrir en Excel o verlas en GitHub desde el móvil).
CARPETA_CSV = CARPETA_DATOS / "csv"

# Carpeta "docs": aquí van las páginas HTML. Se llama así porque GitHub
# Pages puede publicar esta carpeta como una web.
CARPETA_WEB = CARPETA_PROYECTO / "docs"
