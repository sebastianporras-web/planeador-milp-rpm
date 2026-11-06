"""CBC con presupuesto explícito, separado del adaptador de producción."""
from cbc_actual import CBCActual

class CBCBenchmark(CBCActual):
    def __init__(self, **kwargs):
        limite = kwargs.pop('timeLimit')
        opciones = list(kwargs.pop('options', []))
        opciones += [f'seconds {float(limite)}', 'timeMode elapsed']
        super().__init__(timeLimit=None, options=opciones, **kwargs)
