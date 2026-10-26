import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from referencia_monte_carlo import validar_referencia, leer_referencia
import test_revision
import rpm_core as core

class Referencia(unittest.TestCase):
    def base(self):
        return dict(n=10, positive_count=10, media_pct=2., mediana_pct=2.,
                    sd_pct=.1, se_pct=.03, ci95_low_pct=1.9, ci95_high_pct=2.1,
                    min_pct=1., max_pct=3., methodology_note='Datos artificiales de prueba')
    def test_rechaza_tipos_no_finitos_y_rangos(self):
        for key, value in [('n', True), ('n', 0), ('positive_count', 11),
                           ('media_pct', '2'), ('media_pct', float('nan')),
                           ('max_pct', float('inf')), ('sd_pct', -1),
                           ('ci95_low_pct', 4), ('mediana_pct', 7),
                           ('methodology_note', '')]:
            with self.subTest(key=key, value=value):
                data=self.base(); data[key]=value
                with self.assertRaises(ValueError): validar_referencia(data)
    def test_archivo_actualizado_y_bom(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'monte_carlo_reference.json'
            data=self.base(); path.write_text(json.dumps(data), encoding='utf-8-sig')
            self.assertEqual(leer_referencia(folder), data)
            data['media_pct']=2.2; path.write_text(json.dumps(data), encoding='utf-8')
            self.assertEqual(leer_referencia(folder)['media_pct'], 2.2)

class Escenarios(unittest.TestCase):
    def test_auditoria_del_resultado_no_global(self):
        fixture=test_revision.Revision(); fixture.setUp()
        previous=core.ULTIMA_AUDITORIA
        original=core.resolver_asignacion
        def resolver_y_cambiar_global(*args, **kwargs):
            result=original(*args, **kwargs)
            core.ULTIMA_AUDITORIA={'ajeno': True}
            return result
        try:
            with patch.object(core, 'resolver_asignacion', side_effect=resolver_y_cambiar_global):
                result=core._resolver_escenario(fixture.C, fixture.D, fixture.S, fixture.cap)
            records=list(Path(fixture.temp.name).glob('*.json'))
            self.assertEqual(len(records), 1)
            saved=json.loads(records[0].read_text())
            self.assertNotIn('ajeno', saved['auditoria'])
            self.assertEqual(saved['auditoria'], result['auditoria_solver'])
        finally:
            core.ULTIMA_AUDITORIA=previous
            fixture.tearDown()

if __name__=='__main__': unittest.main()
