"""Reconstruye el resumen de la evidencia guardada; no ejecuta una simulación."""
from pathlib import Path
import hashlib
import json
import math
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent

def construir_referencia():
    source = ROOT / 'evidencia_estudio/tablas/monte_carlo_escenarios.csv'
    frame = pd.read_csv(source)
    values = 100 * (1 - frame['objective'] / frame['heuristica_objetivo'])
    if len(frame) != 1000 or frame.escenario.nunique() != 1000:
        raise ValueError('La evidencia histórica requiere 1000 escenarios únicos.')
    if not np.isfinite(values).all() or not (frame.heuristica_faltantes == 0).all():
        raise ValueError('La comparación requiere resultados finitos y heurística factible.')
    if not frame.feasible.eq(True).all():
        raise ValueError('La evidencia contiene escenarios sin plan factible.')
    if not np.allclose(values, frame.mejora_incumbente_pct, rtol=0, atol=1e-9):
        raise ValueError('Los objetivos no reproducen las mejoras registradas.')
    n = len(values); mean = float(values.mean()); sd = float(values.std(ddof=1))
    se = sd / math.sqrt(n)
    q = values.quantile([.05,.25,.50,.75,.95])
    return dict(reference_type='historico_revalidado', status='planes_factibles_auditados',
        methodology_note='Evidencia histórica: 1000 escenarios independientes U(0,85;1,15), semilla 42, matriz MODELO PL. Mejora de planes factibles frente a una heurística factible; no son 1000 óptimos certificados. El protocolo histórico utilizó 5 s por escenario y reintentó tres casos a 30 s. Este protocolo es distinto del plan operativo actual sin límite interno. IC normal de la media: media ± 1,96·s/√n.',
        n=n, seed=42, uniform_low=.85, uniform_high=1.15,
        media_pct=mean, mediana_pct=float(values.median()), sd_pct=sd,
        cv_pct=100*sd/mean, se_pct=se, iqr_pct=float(q.loc[.75]-q.loc[.25]),
        min_pct=float(values.min()), max_pct=float(values.max()),
        ci95_low_pct=mean-1.96*se, ci95_high_pct=mean+1.96*se,
        positive_count=int((values>0).sum()),
        n_gap_cero=int(frame.certified_zero_gap.eq(True).sum()),
        max_gap_pct=float(frame.gap_pct.max()), mean_gap_pct=float(frame.gap_pct.mean()),
        cuantiles_pct={str(k):float(v) for k,v in q.items()},
        source_path=source.relative_to(ROOT).as_posix(),
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        previous_reference_path='evidencia_estudio/historico/monte_carlo_reference_anterior.json')

if __name__ == '__main__':
    data=construir_referencia()
    from referencia_monte_carlo import validar_referencia
    validar_referencia(data)
    (ROOT/'monte_carlo_reference.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"Resumen reconstruido desde {data['n']} escenarios; media {data['media_pct']:.10f} %.")
