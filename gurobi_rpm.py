"""Credenciales privadas: se transportan por entorno, nunca por archivos del lote."""
import importlib.util
import os

KEYS = ('WLSACCESSID', 'WLSSECRET', 'LICENSEID')

def credenciales():
    values = {k: os.environ.get(k, '').strip() for k in KEYS}
    # Streamlit sólo en el servidor de la interfaz; el worker hereda su entorno.
    try:
        import streamlit as st
        from streamlit.runtime import exists
        if exists():
            for k in KEYS:
                value = st.secrets.get(k, values[k])
                values[k] = str(value).strip()
    except (FileNotFoundError, KeyError):
        pass
    return values

def disponibles():
    solvers = ['HiGHS', 'CBC']
    if importlib.util.find_spec('gurobipy') and all(credenciales().values()):
        solvers.append('Gurobi')
    return solvers

def entorno_worker():
    env = os.environ.copy()
    env.update({k: v for k, v in credenciales().items() if v})
    return env
