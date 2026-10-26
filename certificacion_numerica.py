"""Certificado numérico: conservar cotas y GAP originales; no redondearlos."""
import math
GAP_REL_TOL = 1e-9
BOUND_ABS_TOL = 1e-7
FACTIBILITY_TOL = 1e-5

def cierre_numerico(gap, lb, ub):
    """Solo cierre numérico. El llamador también exige estado óptimo y factibilidad.

    GAP es fracción, no porcentaje. La diferencia absoluta limita la aceptación
    incluso si la escala del objetivo hace diminuto un GAP relativo sustantivo.
    """
    try:
        gap, lb, ub = map(float, (gap, lb, ub))
    except (TypeError, ValueError):
        return False
    return (all(math.isfinite(v) for v in (gap, lb, ub))
            and 0 <= gap <= GAP_REL_TOL and abs(ub-lb) <= BOUND_ABS_TOL)

class ResolucionNoCertificada(RuntimeError):
    def __init__(self, mensaje, auditoria):
        super().__init__(mensaje)
        self.auditoria = dict(auditoria)
