import sys
import unittest
import json
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from actualizar_referencia_monte_carlo import construir_referencia

class EvidenciaPublicada(unittest.TestCase):
    def test_json_reproduce_csv(self):
        saved=json.loads((ROOT/'monte_carlo_reference.json').read_text(encoding='utf-8'))
        actual=construir_referencia()
        self.assertEqual(saved.keys(),actual.keys())
        # NumPy/pandas pueden cambiar el último bit de un estadístico.
        # La huella del CSV, los conteos y los campos de texto siguen siendo exactos.
        for key,value in saved.items():
            with self.subTest(campo=key):
                if isinstance(value,float):
                    self.assertTrue(np.isfinite(actual[key]))
                    self.assertAlmostEqual(value,actual[key],delta=1e-12)
                else:
                    self.assertEqual(value,actual[key])
        self.assertEqual(saved['n_gap_cero'],0)
        self.assertAlmostEqual(saved['media_pct'],15.18760551240193,places=10)
    def test_auditoria_nominal_completa(self):
        table=pd.read_csv(ROOT/'evidencia_estudio/tablas/auditoria_independiente.csv')
        self.assertEqual(len(table),60)
        self.assertEqual(table.corrida.nunique(),60)
        self.assertTrue(table.verificacion.eq('CUMPLE').all())
        errors=table.drop(columns=['corrida','objetivo_recalculado','verificacion'])
        self.assertTrue(np.isfinite(errors.to_numpy()).all())
        self.assertLessEqual(errors.to_numpy().max(),1e-5)

if __name__=='__main__':unittest.main()
