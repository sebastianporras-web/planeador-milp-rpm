"""Horizonte mínimo para una demanda FIJA. Prueba independiente del costo óptimo."""
import hashlib
import json
import tempfile
from pathlib import Path
import pandas as pd
from motor_horizonte import Datos, buscar


def preparar(C, D, S, capacidad):
    D = D.reindex(C.index)
    if D.isna().any() or (D < 0).any():
        raise ValueError('Demanda incompleta o negativa.')
    C = C.loc[D > 0]
    D = D.loc[C.index]
    if C.empty:
        raise ValueError('No hay demanda positiva para planificar.')
    S = S.reindex(C.columns)
    caps = capacidad.reindex(C.columns) if isinstance(capacidad, pd.Series) else pd.Series(float(capacidad), index=C.columns)
    ids = list(map(str, C.index))
    payload = dict(ids=ids, maquinas=list(map(str, C.columns)),
                   C=C.to_numpy(float).tolist(), D=D.to_numpy(float).tolist(),
                   S=S.to_numpy(float).tolist(), cap=caps.to_numpy(float).tolist(),
                   nombres=[dict(ID=i, Producto=i) for i in ids], notas=[])
    Datos(payload)  # Rechaza datos inválidos antes de consultar resultados previos.
    return payload


def firma(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


def calcular(C, D, S, capacidad, solver='HiGHS', carpeta=None):
    payload = preparar(C, D, S, capacidad)
    folder = Path(carpeta or tempfile.mkdtemp(prefix='rpm_horizonte_'))
    state = buscar(Datos(payload), folder, solver)
    state.update(datos_sha256=firma(payload), carpeta_evidencia=str(folder), solver_busqueda=solver)
    return state


def obtener(st, C, D, S, capacidad, solver='HiGHS', clave=''):
    """Reutiliza sólo la prueba de horizonte para entradas idénticas, nunca las corridas del lote."""
    key = 'horizonte_auto_v1_' + firma(preparar(C, D, S, capacidad))
    if key not in st.session_state:
        with st.spinner('Calculando el mínimo de días para completar la demanda...'):
            st.session_state[key] = calcular(C, D, S, capacidad, solver)
    state = st.session_state[key]
    if not state.get('minimo_certificado'):
        st.warning(f"Horizonte pendiente de demostrar: entre {state['inferior']} y {state['superior']} días. No se presenta un óptimo de días.")
        if st.button('Reintentar búsqueda del horizonte', key=key+'_retry'+clave):
            del st.session_state[key]
            st.rerun()
    return state


def horizontes_certificacion(state):
    if not state.get('minimo_certificado'):
        raise ValueError('La comparación automática requiere demostrar primero el mínimo de días.')
    return sorted({1, int(state['horizonte_minimo'])})


def instancias_automaticas(instancias, state):
    """La columna de demanda de mayor plazo conserva sus unidades; sólo cambia H."""
    h = horizontes_certificacion(state)[-1]
    total = instancias[max(instancias)]
    if h == 1:
        return {1: total}
    return {1: instancias.get(1, total), h: total}
