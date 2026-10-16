"""Resultados certificados y planes iniciales. No se utiliza en el benchmark."""
from pathlib import Path
import hashlib
import json
import os
import tempfile
import time
import numpy as np
import pandas as pd
import rpm_core as core

ROOT=Path(__file__).resolve().parent

def codificar(x):
    if isinstance(x,pd.DataFrame):
        return {'_tipo':'tabla','index':x.index.tolist(),'columns':x.columns.tolist(),'data':x.to_numpy().tolist()}
    if isinstance(x,pd.Series):
        return {'_tipo':'serie','index':x.index.tolist(),'data':x.tolist(),'name':x.name}
    if isinstance(x,dict):return {k:codificar(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [codificar(v) for v in x]
    if isinstance(x,np.generic):return x.item()
    return x

def decodificar(x):
    if isinstance(x,dict):
        if x.get('_tipo')=='tabla':return pd.DataFrame(x['data'],index=x['index'],columns=x['columns'])
        if x.get('_tipo')=='serie':return pd.Series(x['data'],index=x['index'],name=x.get('name'))
        return {k:decodificar(v) for k,v in x.items()}
    if isinstance(x,list):return [decodificar(v) for v in x]
    return x

def firma(C,D,S,h,cap,solver="HiGHS"):
    payload=codificar({'C':C,'D':D,'S':S,'h':int(h),'cap':core._serie_capacidades(cap),
        'codigo':hashlib.sha256(b''.join((ROOT/n).read_bytes() for n in ['rpm_core.py','soluciones_guardadas.py','optimizar_rpm.py','solver_config_rpm.py','integracion_selectiva.py','cbc_actual.py','poda_lagrangiana.py'])).hexdigest(),
        'solver':solver,'gap':0})
    return hashlib.sha256(json.dumps(payload,sort_keys=True,allow_nan=False).encode()).hexdigest()

def validar_plan(plan,C,D,S,h,cap):
    caps=core._serie_capacidades(cap);D=core._validar_demanda_entera(D.reindex(C.index))
    if h==1:
        P=plan.reindex(index=C.index,columns=core.MACHINES)
        a=P.to_numpy(float)
        if not np.isfinite(a).all() or (a<0).any() or not np.allclose(a,np.rint(a),atol=1e-7,rtol=0):return False
        return bool(np.array_equal(P.sum(axis=1).to_numpy(),D.to_numpy()) and
                    (((C*P).sum()+P.gt(0).sum()*S)<=caps+1e-6).all())
    P=plan.copy()
    if not {'producto','maquina','dia','unidades'}.issubset(P.columns):return False
    if not P.producto.isin(C.index).all() or not P.maquina.isin(core.MACHINES).all():return False
    if not P.dia.isin(range(1,h+1)).all():return False
    if not np.isfinite(P.unidades).all() or (P.unidades<=0).any() or not np.allclose(P.unidades,np.rint(P.unidades),atol=1e-7,rtol=0):return False
    P=P.groupby(['producto','maquina','dia'],as_index=False).unidades.sum()
    if not np.array_equal(P.groupby('producto').unidades.sum().reindex(C.index,fill_value=0).to_numpy(),D.to_numpy()):return False
    P['carga']=[r.unidades*C.loc[r.producto,r.maquina]+S[r.maquina] for r in P.itertuples()]
    return all(v<=caps[j]+1e-6 for (_,j),v in P.groupby(['dia','maquina']).carga.sum().items())

def resolver(C,D,S,h,cap,usar_guardada=True,usar_inicio=True,carpeta=None,solver="HiGHS"):
    # Carpeta privada de la sesión; la app nunca acepta un archivo serializado del usuario.
    folder=Path(carpeta or tempfile.mkdtemp(prefix='rpm_solutions_'));folder.mkdir(parents=True,exist_ok=True)
    key=firma(C,D,S,h,cap,solver);target=folder/(key+'.json');previous=folder/f'ultimo_{h}d.json'
    def leer(p):
        try:return decodificar(json.loads(p.read_text()))
        except (OSError,ValueError,KeyError):return None
    def plan_de(res):return res['asignacion' if h==1 else 'plan']
    record=leer(target)
    if usar_guardada and record and record.get('firma')==key:
        res=record['resultado']
        if res.get('gap_certificado') and validar_plan(plan_de(res),C,D,S,h,cap):
            return res,{'origen':'Solución guardada certificada','firma':key,'fecha_utc':record['fecha_utc'],'nueva_ejecucion':False}
    initial=None;source='Sin solución inicial'
    if usar_inicio:
        old=leer(previous)
        if old:
            candidate=plan_de(old['resultado'])
            try:valid=validar_plan(candidate,C,D,S,h,cap)
            except (KeyError,ValueError,TypeError):valid=False
            if valid:initial=candidate;source='Plan anterior factible verificado'
            else:source='Plan anterior descartado: no es factible con los datos actuales'
        if h==3 and (ROOT/'plan_inicial_3d.csv').exists():
            candidate=pd.read_csv(ROOT/'plan_inicial_3d.csv')
            if validar_plan(candidate,C,D,S,h,cap):
                def costo_plan(p):
                    p=p.groupby(['producto','maquina','dia'],as_index=False).unidades.sum()
                    return sum(r.unidades*C.loc[r.producto,r.maquina]+S[r.maquina] for r in p.itertuples())
                if initial is None or costo_plan(candidate)<costo_plan(initial)-1e-7:
                    initial=candidate;source='Mejor plan incluido factible verificado (no certificado como óptimo)'
    token=core.RUN_CONTEXT.set({'solver':solver,'log_dir':str(folder/'logs'),'run_id':f'{h}d_{time.time_ns()}'})
    try:
        res=(core.resolver_asignacion(C,D,S,cap,plan_inicial=initial) if h==1 else
             core.resolver_multidia(C,D,S,h,cap_minutos=cap,plan_inicial=initial))
    finally:
        core.RUN_CONTEXT.reset(token)
    if not res.get('gap_certificado'):raise RuntimeError('No se guarda una solución sin certificado.')
    record={'firma':key,'fecha_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'resultado':res}
    text=json.dumps(codificar(record),ensure_ascii=False,allow_nan=False)
    for p in [target,previous]:
        tmp=p.with_suffix('.tmp');tmp.write_text(text);tmp.replace(p)
    return res,{'origen':source,'firma':key,'fecha_utc':record['fecha_utc'],'nueva_ejecucion':True}
