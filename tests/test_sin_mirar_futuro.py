# tests/test_sin_mirar_futuro.py
# Pruebas automáticas contra el "look-ahead bias" (mirar el futuro sin querer).
#
# Cómo se ejecutan (desde la carpeta del proyecto):
#     python -m unittest discover tests
#
# Idea de cada prueba: si una decisión del día D usara, aunque sea por error,
# algún dato posterior a D, entonces cambiar o borrar esos datos futuros
# cambiaría la decisión. Comprobamos que NO cambia.

import sys
import unittest
from pathlib import Path

# Para poder importar los módulos del proyecto (están en la carpeta de arriba).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import almacen  # noqa: E402
import backtest as bt  # noqa: E402
import senales  # noqa: E402

# Fechas de corte: días de crisis y días normales.
FECHAS_CORTE = ["2008-09-15", "2009-03-09", "2012-06-01", "2020-03-16", "2022-06-16"]


class TestSinMirarFuturo(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Se ejecuta una vez: cargamos los datos completos.
        cls.cierres = almacen.leer_cierres_diarios(["^GSPC", "^VIX"])
        cls.completas = senales.calcular_senales(cierres=cls.cierres)
        cls.tabla = bt.preparar_datos()

    def test_senal_no_cambia_si_borramos_el_futuro(self):
        # Calculamos las señales SOLO con datos hasta el día D y comparamos
        # con las calculadas con TODO el histórico: hasta D deben ser iguales.
        for corte in FECHAS_CORTE:
            with self.subTest(corte=corte):
                recortadas = senales.calcular_senales(cierres=self.cierres.loc[:corte])
                comunes = recortadas.index
                self.assertTrue(recortadas["senal"].equals(self.completas.loc[comunes, "senal"]))
                for columna in ["media_corta", "media_larga", "rsi", "regimen"]:
                    self.assertTrue(recortadas[columna].equals(self.completas.loc[comunes, columna]),
                                    f"{columna} cambia al borrar el futuro")

    def test_cartera_no_cambia_si_alteramos_precios_futuros(self):
        # Duplicamos todos los precios de SPY posteriores al día D.
        # El valor de la cartera hasta D no puede cambiar.
        posicion = bt.estrategia_completa(self.tabla)
        normal = bt.simular(self.tabla, posicion)["valor"]
        for corte in FECHAS_CORTE:
            with self.subTest(corte=corte):
                alterada = self.tabla.copy()
                futuro = alterada.index > corte
                alterada.loc[futuro, ["apertura", "cierre"]] *= 2
                valor = bt.simular(alterada, posicion)["valor"]
                self.assertTrue(valor.loc[:corte].equals(normal.loc[:corte]))

    def test_operaciones_al_dia_siguiente_en_la_apertura(self):
        # Cada compra o venta debe ocurrir el día de bolsa SIGUIENTE a la
        # señal que la provocó, al precio de APERTURA (más deslizamiento).
        posicion = bt.estrategia_completa(self.tabla)
        # Posición efectiva deseada cada día (MANTENER = seguir con la anterior).
        deseada = posicion.ffill()
        dias = list(self.tabla.index)
        for op in bt.simular(self.tabla, posicion)["operaciones"]:
            entrada = op["entrada"]
            anterior = dias[dias.index(entrada) - 1]
            self.assertEqual(deseada.loc[anterior], 1, f"compra del {entrada:%d/%m/%Y} sin señal el día anterior")
            esperado = self.tabla.loc[entrada, "apertura"] * (1 + bt.DESLIZAMIENTO)
            self.assertAlmostEqual(op["precio_entrada"], esperado, places=6)
            if not op.get("sigue_abierta"):
                salida = op["salida"]
                anterior = dias[dias.index(salida) - 1]
                self.assertEqual(deseada.loc[anterior], 0, f"venta del {salida:%d/%m/%Y} sin señal el día anterior")
                esperado = self.tabla.loc[salida, "apertura"] * (1 - bt.DESLIZAMIENTO)
                self.assertAlmostEqual(op["precio_salida"], esperado, places=6)

    def test_control_la_trampa_si_se_detecta(self):
        # "Control negativo": activamos A PROPÓSITO la versión tramposa
        # (ejecutar al cierre del mismo día de la señal) y comprobamos que la
        # prueba de los precios futuros SÍ la detecta. Si no la detectara,
        # las pruebas de arriba no servirían de nada.
        posicion = bt.estrategia_completa(self.tabla)
        normal = bt.simular(self.tabla, posicion)["operaciones"]
        tramposa = bt.simular(self.tabla, posicion, ejecutar_mismo_dia=True)["operaciones"]
        # La tramposa compra un día ANTES que la honesta (el mismo día de la señal).
        dias = list(self.tabla.index)
        for honesta, trampa in zip(normal, tramposa):
            self.assertEqual(dias.index(trampa["entrada"]), dias.index(honesta["entrada"]) - 1)


if __name__ == "__main__":
    unittest.main()
