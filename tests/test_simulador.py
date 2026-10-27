# tests/test_simulador.py
# Pruebas del simulador en vivo (Fase 4).
#
# La más importante: el simulador debe dar EXACTAMENTE el mismo resultado
# que el backtest con las mismas fechas. Si no, estaríamos probando en vivo
# una estrategia distinta de la que verificamos en las fases 3 y 3b.
#
# Cómo se ejecutan:   python -m unittest discover tests

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import backtest as bt  # noqa: E402
import simulador as sim  # noqa: E402

NUEVA_YORK = ZoneInfo("America/New_York")
# Un periodo con de todo: subidas, COVID (2020) y la bajista de 2022.
DESDE, HASTA = "2019-06-03", "2022-12-30"


def a_las(fecha, hora, minuto=0):
    # Un momento concreto de un día, en hora de Nueva York, pasado a UTC.
    return datetime(fecha.year, fecha.month, fecha.day, hora, minuto, tzinfo=NUEVA_YORK).astimezone(timezone.utc)


class TestSimulador(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tabla = bt.preparar_datos().loc[DESDE:HASTA]

    def setUp(self):
        # Cada prueba usa su propia base de datos temporal (se borra al final).
        self.carpeta = tempfile.TemporaryDirectory()
        self.base = Path(self.carpeta.name) / "cartera.db"

    def tearDown(self):
        self.carpeta.cleanup()

    def comprobar_igual_que_backtest(self, valores, operaciones):
        for clave, info in sim.ESTRATEGIAS.items():
            esperado = bt.simular(self.tabla, info["posicion"](self.tabla))
            v = valores[valores.estrategia == clave].set_index("fecha")["valor"]
            self.assertEqual(len(v), len(esperado["valor"]))
            # Mismo valor de cartera cada día (hasta la última décima de céntimo).
            for fecha, valor in esperado["valor"].items():
                self.assertAlmostEqual(v[f"{fecha:%Y-%m-%d}"], valor, places=6)
            # Mismas compras: mismas fechas y mismos precios.
            compras = operaciones[(operaciones.estrategia == clave) & (operaciones.tipo == "COMPRA")]
            self.assertEqual(list(compras.fecha), [f"{o['entrada']:%Y-%m-%d}" for o in esperado["operaciones"]])
            for precio, o in zip(compras.precio, esperado["operaciones"]):
                self.assertAlmostEqual(precio, o["precio_entrada"], places=8)

    def test_igual_que_el_backtest_dia_a_dia(self):
        # Simulamos que GitHub lo ejecuta cada noche a las 20:00 de Nueva York.
        for fecha in self.tabla.index:
            sim.ejecutar(self.base, self.tabla, ahora=a_las(fecha, 20))
        _, operaciones, valores, _ = sim.leer(self.base)
        self.comprobar_igual_que_backtest(valores, operaciones)
        # Todas las órdenes se decidieron la noche anterior: ninguna "recuperada".
        self.assertEqual(operaciones["recuperada"].sum(), 0)
        self.assertGreater(len(operaciones), 2)

    def test_igual_que_el_backtest_aunque_falten_dias(self):
        # Si GitHub se salta noches, se recupera todo de golpe con el mismo
        # resultado, pero las operaciones quedan marcadas como "recuperadas".
        primero = self.tabla.index[0]
        sim.ejecutar(self.base, self.tabla, ahora=a_las(primero, 20))
        sim.ejecutar(self.base, self.tabla, ahora=a_las(self.tabla.index[-1], 23))
        _, operaciones, valores, _ = sim.leer(self.base)
        self.comprobar_igual_que_backtest(valores, operaciones)
        # Las órdenes ejecutadas el segundo día se decidieron a tiempo (en la
        # primera noche); todas las demás se decidieron tarde, al recuperar
        # los días perdidos, y deben quedar marcadas.
        segundo = f"{self.tabla.index[1]:%Y-%m-%d}"
        a_tiempo = operaciones[operaciones.fecha == segundo]
        tarde = operaciones[operaciones.fecha > segundo]
        self.assertGreater(len(a_tiempo), 0)
        self.assertEqual(a_tiempo["recuperada"].sum(), 0)
        self.assertEqual(tarde["recuperada"].sum(), len(tarde))

    def test_no_procesa_un_dia_con_la_bolsa_abierta(self):
        # Ejecutado a mediodía, el día de hoy (precios a medias) se ignora.
        dia = self.tabla.index[5]
        sim.ejecutar(self.base, self.tabla, ahora=a_las(dia, 12))
        _, _, valores, _ = sim.leer(self.base)
        self.assertEqual(valores["fecha"].max(), f"{self.tabla.index[4]:%Y-%m-%d}")

    def test_pausar_y_reanudar(self):
        dias = self.tabla.index
        sim.ejecutar(self.base, self.tabla, ahora=a_las(dias[0], 20))
        sim.pausar("spy", self.base)
        sim.ejecutar(self.base, self.tabla, ahora=a_las(dias[10], 20))
        _, operaciones, valores, _ = sim.leer(self.base)
        # Pausada desde el primer día: SPY no llegó a comprar, pero su valor
        # se sigue apuntando cada día. La estrategia completa sigue normal.
        self.assertEqual((operaciones.estrategia == "spy").sum(), 0)
        self.assertEqual((valores.estrategia == "spy").sum(), 11)
        sim.reanudar("spy", self.base)
        sim.ejecutar(self.base, self.tabla, ahora=a_las(dias[12], 20))
        _, operaciones, _, _ = sim.leer(self.base)
        compras = operaciones[operaciones.estrategia == "spy"]
        # Reanudada: la señal del día 11 compra en la apertura del día 12.
        self.assertEqual(list(compras.fecha), [f"{dias[12]:%Y-%m-%d}"])

    def test_reiniciar(self):
        dias = self.tabla.index
        sim.ejecutar(self.base, self.tabla, ahora=a_las(dias[0], 20))
        sim.ejecutar(self.base, self.tabla, ahora=a_las(dias[5], 20))
        sim.reiniciar("completa", self.base)
        carteras, operaciones, valores, eventos = sim.leer(self.base)
        self.assertNotIn("completa", carteras)
        self.assertEqual((valores.estrategia == "completa").sum(), 0)
        self.assertIn("spy", carteras)  # la otra no se toca
        # Al volver a ejecutar, empieza de cero con 10.000 USD.
        sim.ejecutar(self.base, self.tabla, ahora=a_las(dias[8], 20))
        carteras, _, valores, _ = sim.leer(self.base)
        self.assertEqual(carteras["completa"]["inicio"], f"{dias[8]:%Y-%m-%d}")
        primero = valores[valores.estrategia == "completa"]["valor"].iloc[0]
        self.assertEqual(primero, bt.CAPITAL_INICIAL)


if __name__ == "__main__":
    unittest.main()
