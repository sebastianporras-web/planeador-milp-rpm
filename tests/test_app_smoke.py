"""Pruebas breves de la interfaz. No ejecutan el benchmark ni necesitan WLS."""
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def horizonte_simulado(*args, **kwargs):
    """Solo sustituye la búsqueda costosa de horizonte en esta prueba de interfaz."""
    return {
        "minimo_certificado": True,
        "horizonte_minimo": 3,
        "inferior": 3,
        "superior": 3,
    }


class PruebaInterfaz(unittest.TestCase):
    def abrir(self):
        with patch("horizonte_automatico.obtener", side_effect=horizonte_simulado):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        return app

    def test_estudio_carga_datos_y_panel(self):
        app = self.abrir()
        self.assertTrue(any("Planeación de producción" in x.value for x in app.title))
        self.assertTrue(any(x.label == "Iniciar comparación" for x in app.button))
        self.assertTrue(any("Horizonte mínimo" in x.label for x in app.metric))

    def test_demanda_total_sin_archivo_muestra_guia(self):
        app = self.abrir()
        app.radio[0].set_value("Demanda total · horizonte automático")
        app.run(timeout=90)
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        self.assertGreaterEqual(len(app.info), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
