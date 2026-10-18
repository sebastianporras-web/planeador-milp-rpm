"""Lectura de demanda total y máquinas variables. No altera el anexo histórico."""
import io
import hashlib
import numpy as np
import pandas as pd

SETUPS_ESTUDIO={'M1':98.666,'M2':94.,'M3':55.58,'M4':60.,'M5':19.45,
                'M6':72.5,'M7':14.65,'M8':14.65,'M9':33.,'M10':85.}

def leer(data, unidad='Segundos', duplicados='Perfil conservador'):
    book=pd.ExcelFile(io.BytesIO(data))
    if {'Referencias','Recursos'}.issubset(book.sheet_names):
        R=pd.read_excel(book,'Referencias',dtype={'ID':str,'Producto':str})
        M=pd.read_excel(book,'Recursos',dtype={'Maquina':str})
        required={'ID','Producto','Demanda_total'}
        if not required.issubset(R): raise ValueError('Referencias requiere ID, Producto y Demanda_total.')
        if not {'Maquina','Setup_min','Capacidad_min_dia'}.issubset(M):
            raise ValueError('Recursos requiere Maquina, Setup_min y Capacidad_min_dia.')
        if R[list(required)].isna().any().any() or M.Maquina.isna().any(): raise ValueError('Hay identificadores vacíos.')
        M.Maquina=M.Maquina.str.strip();R.ID=R.ID.str.strip();R.Producto=R.Producto.str.strip()
        if R.ID.eq('').any() or R.Producto.eq('').any():raise ValueError('ID y Producto no pueden estar vacíos.')
        if M.Maquina.duplicated().any() or R.ID.duplicated().any(): raise ValueError('ID y Maquina deben ser únicos.')
        machines=M.Maquina.tolist()
        if not machines or any(not m for m in machines) or any(m not in R for m in machines):
            raise ValueError('Cada máquina de Recursos debe tener una columna de tiempos en Referencias.')
        extra=set(R.columns)-required-set(machines)
        if extra:raise ValueError('Hay columnas sin máquina declarada en Recursos: '+', '.join(map(str,sorted(extra))))
        names=R[['ID','Producto']].copy();q=pd.to_numeric(R.Demanda_total,errors='raise')
        C=R[machines].apply(pd.to_numeric,errors='raise');C.index=R.ID
        notes=['Tiempos de Referencias interpretados según la unidad seleccionada. Cero = asignación no habilitada.']
        if 'Instrucciones' in book.sheet_names:
            instructions=pd.read_excel(book,'Instrucciones')
            if {'Concepto','Valor'}.issubset(instructions):
                notes.extend(instructions.loc[instructions.Concepto.eq('Supuesto'),'Valor'].dropna().astype(str).tolist())
        source='Plantilla flexible con identificadores explícitos'
    elif {'Demanda','Maquinas'}.issubset(book.sheet_names):
        D=pd.read_excel(book,'Demanda');T=pd.read_excel(book,'Maquinas')
        if 'PRODUCTO' not in D or 'UNIDADES VENDIDAS' not in D or 'PRODUCTO' not in T:
            raise ValueError('Se requieren PRODUCTO, UNIDADES VENDIDAS y PRODUCTO en Maquinas.')
        for frame in (D,T):
            if frame.PRODUCTO.isna().any(): raise ValueError('Hay nombres de producto vacíos.')
            frame.PRODUCTO=frame.PRODUCTO.astype(str).str.strip()
            if frame.PRODUCTO.eq('').any():raise ValueError('Hay nombres de producto vacíos.')
        machines=[str(c) for c in T.columns if c!='PRODUCTO']
        if not machines or len(set(machines))!=len(machines):raise ValueError('Máquinas vacías o duplicadas.')
        values=T[machines].apply(pd.to_numeric,errors='raise')
        if not np.isfinite(values.to_numpy()).all() or (values<0).any().any():
            raise ValueError('Los tiempos deben ser finitos y no negativos.')
        if set(D.PRODUCTO)!=set(T.PRODUCTO):raise ValueError('Las hojas no contienen los mismos nombres de producto.')
        repeated=T.PRODUCTO.duplicated(keep=False)
        if repeated.any() and duplicados=='Exigir identificadores únicos':
            raise ValueError('Hay nombres repetidos. Usa la plantilla con ID o acepta el perfil conservador documentado.')
        # Perfil de peor tiempo; intersección de máquinas habilitadas.
        grouped=values.groupby(T.PRODUCTO)
        profile=grouped.max().where(grouped.min()>0,0.)
        ids=[f'R{i+1:06d}' for i in range(len(D))]
        C=profile.loc[D.PRODUCTO].copy();C.index=ids
        names=pd.DataFrame({'ID':ids,'Producto':D.PRODUCTO.tolist()})
        q=pd.to_numeric(D['UNIDADES VENDIDAS'],errors='raise')
        M=pd.DataFrame({'Maquina':machines,'Setup_min':[SETUPS_ESTUDIO.get(m,np.nan) for m in machines],
                        'Capacidad_min_dia':[1440.]*len(machines)})
        notes=[f'{len(D)} filas de demanda conservadas; {D.PRODUCTO.nunique()} nombres únicos. No se suman ni eliminan pedidos.',
               'Si un nombre tiene varias observaciones, cada pedido conserva su ID y recibe el máximo tiempo por máquina. Se habilita una máquina solo si TODAS las observaciones del nombre tienen tiempo positivo.',
               'Los pedidos de nombre repetido se tratan como referencias independientes: cada uno genera sus propias preparaciones. El horizonte corresponde a este supuesto conservador, no a una identificación física verificada.',
               'Setup y capacidad propuestos provienen del estudio anterior (M1–M10); revisarlos antes de resolver. Las máquinas nuevas requieren completar Setup_min.']
        source='Demanda/Maquinas con perfiles conservadores por nombre'
    else:raise ValueError('Usa Demanda + Maquinas, o Referencias + Recursos (plantilla flexible).')
    if unidad not in ('Segundos','Minutos'):raise ValueError('Unidad desconocida.')
    if not len(C) or not np.isfinite(C.to_numpy()).all() or (C<0).any().any():raise ValueError('Tiempos inválidos.')
    if not np.isfinite(q).all() or (q<0).any() or (q!=np.rint(q)).any():raise ValueError('La demanda debe ser entera no negativa.')
    if float(q.sum())<=0:raise ValueError('La demanda total debe ser positiva.')
    q=pd.Series(q.to_numpy(dtype='int64'),index=C.index,name='Demanda_total')
    C=C.astype(float)/(60. if unidad=='Segundos' else 1.)
    positive=q>0;C=C.loc[positive];q=q.loc[positive];names=names[names.ID.isin(C.index)]
    if C.le(0).all(axis=1).any():raise ValueError('Hay pedidos sin máquina habilitada; corrige tiempos/códigos antes de resolver.')
    return dict(C=C,D=q,nombres=names,recursos=M,notas=notes,origen=source,
                archivo_sha256=hashlib.sha256(data).hexdigest(),unidad_original=unidad)

def serializar(datos,recursos):
    C=datos['C'];D=datos['D'];M=recursos.copy().set_index('Maquina').reindex(C.columns)
    for k in ['Setup_min','Capacidad_min_dia']:M[k]=pd.to_numeric(M[k],errors='raise')
    if not np.isfinite(M.to_numpy(dtype=float)).all():raise ValueError('Completa las preparaciones y capacidades de todas las máquinas.')
    if (M.Setup_min<0).any() or (M.Capacidad_min_dia<=0).any() or (M.Capacidad_min_dia>1440).any():
        raise ValueError('Setup debe ser no negativo; la capacidad diaria de cada máquina debe estar entre 0 y 1440 minutos, excluido cero.')
    return dict(ids=C.index.tolist(),maquinas=C.columns.tolist(),C=C.to_numpy().tolist(),D=D.tolist(),
                S=M.Setup_min.tolist(),cap=M.Capacidad_min_dia.tolist(),
                nombres=datos['nombres'].to_dict('records'),notas=datos['notas'],origen=datos['origen'],
                archivo_sha256=datos['archivo_sha256'],unidad_original=datos['unidad_original'])
