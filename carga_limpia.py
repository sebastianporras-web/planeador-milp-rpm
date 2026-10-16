"""Contrato de entrada v7. Tiempos en minutos; demandas explícitas por horizonte."""
import numpy as np
import pandas as pd
from rpm_core import MACHINES


def cargar(fuente):
    xls = pd.ExcelFile(fuente)
    if not {'Referencias', 'Maquinas'}.issubset(xls.sheet_names):
        raise ValueError('Usa la plantilla de dos hojas: Referencias y Maquinas. El anexo histórico se abre desde la opción Datos del estudio.')
    d = pd.read_excel(xls, 'Referencias', dtype={'Referencia': str}).dropna(how='all')
    s = pd.read_excel(xls, 'Maquinas', dtype={'Maquina': str}).dropna(how='all')
    expected = ['Referencia', 'Demanda_1d', 'Demanda_3d'] + MACHINES
    if list(d.columns) != expected or list(s.columns) != ['Maquina', 'Setup_min']:
        raise ValueError('Conserva los encabezados y su orden en ambas hojas. Descarga la plantilla vigente.')
    if d.empty:
        raise ValueError('La plantilla está vacía. Completa una referencia por fila y sus tiempos antes de cargarla.')
    if d.Referencia.isna().any() or s.Maquina.isna().any():
        raise ValueError('Hay filas con datos pero sin nombre de referencia o máquina.')
    d.Referencia = d.Referencia.str.strip(); s.Maquina = s.Maquina.str.strip()
    if d.Referencia.eq('').any() or d.Referencia.duplicated().any():
        raise ValueError('Cada referencia debe tener un nombre no vacío y único.')
    # PuLP normaliza estos caracteres al crear nombres. Evitar colisiones de etiquetas.
    keys = d.Referencia.str.replace(r'[-+\[\] >/]','_',regex=True)
    if keys.duplicated().any():
        raise ValueError('Dos referencias producen la misma etiqueta interna. Usa códigos únicos que también se distingan por letras o números.')
    if s.Maquina.duplicated().any() or set(s.Maquina) != set(MACHINES):
        raise ValueError('Maquinas debe contener M1 a M10, una vez cada una.')
    C = d.set_index('Referencia')[MACHINES].apply(pd.to_numeric, errors='coerce')
    S = pd.to_numeric(s.set_index('Maquina').Setup_min, errors='coerce').reindex(MACHINES)
    if not np.isfinite(C.to_numpy(float)).all() or (C <= 0).any().any():
        raise ValueError('Completa M1 a M10 con tiempos numéricos positivos en min/unidad. No uses ceros ni celdas vacías para representar incompatibilidad.')
    if not np.isfinite(S.to_numpy(float)).all() or (S < 0).any():
        raise ValueError('Completa Setup_min con minutos numéricos no negativos para las diez máquinas.')
    inst = {}
    for h in (1, 3):
        raw = d[f'Demanda_{h}d']
        if raw.isna().all():
            continue
        values = pd.to_numeric(raw, errors='coerce').to_numpy(float)
        if not np.isfinite(values).all() or (values < 0).any() or (abs(values - np.rint(values)) > 1e-8).any():
            raise ValueError(f'Demanda_{h}d debe contener unidades enteras no negativas en todas las filas. Usa 0 si una referencia no tiene demanda; deja toda la columna vacía si no usarás ese horizonte.')
        D = pd.Series(values.astype(int), index=C.index, name=f'Demanda_{h}d')
        D = D[D > 0]
        if not D.empty:
            inst[h] = (C.loc[D.index].astype(float), D, S.astype(float))
    if not inst:
        raise ValueError('Completa al menos un horizonte con demanda positiva.')
    return inst
