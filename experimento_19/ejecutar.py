"""Ejecutor por bloques. Una resolución por instancia y método; sin herencia."""
from pathlib import Path
import argparse
import hashlib
import itertools
import json
import math
import os
import platform
import subprocess
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from experimento_19.modelo import construir, auditar, heuristica, arrays

METODOS=['Heuristica','CBC','HiGHS','Gurobi']


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def guardar(p, o):
    def limpiar(x):
        if isinstance(x,dict):return {k:limpiar(v) for k,v in x.items()}
        if isinstance(x,list):return [limpiar(v) for v in x]
        if isinstance(x,float) and not math.isfinite(x):return None
        return x
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix('.tmp');tmp.write_bytes((json.dumps(limpiar(o),ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8'));tmp.replace(p)


def codigo():
    files=list((ROOT/'experimento_19').glob('*.py'))+[ROOT/'cbc_actual.py',ROOT/'certificacion_numerica.py']
    return {str(p.relative_to(ROOT)):sha(p) for p in sorted(files)}


def worker(instancia, metodo, salida, limite):
    import pulp
    from experimento_19.solver_benchmark import resolver
    salida=Path(salida);salida.mkdir(parents=True,exist_ok=True)
    inst=json.loads(Path(instancia).read_text(encoding='utf-8'));d=inst['datos']
    r=dict(id=inst['meta']['id'],metodo=metodo,entrada_sha256=sha(instancia),
           meta=inst['meta'],horizonte_dias=d['horizonte_dias'],warm_start=False,
           limite_s=limite,hilos=1,semilla=42,python=sys.version,sistema=platform.platform(),
           cpu=platform.processor(),cpu_logicas=os.cpu_count(),pulp=pulp.__version__,
           codigo_sha256=codigo(),certificado=False,factible=False,estado='Error')
    inicio=time.perf_counter()
    try:
        C,D,S,cap,h=arrays(d)
        if metodo=='Heuristica':
            ini=time.perf_counter();X,Y=heuristica(d)
            r.update(segundos_metodo=time.perf_counter()-ini,estado='Heuristica completada')
        else:
            ini=time.perf_counter();p,x,y=construir(d)
            r['segundos_construccion']=time.perf_counter()-ini
            p.writeLP(str(salida/'modelo.lp'));r['modelo_sha256']=sha(salida/'modelo.lp')
            r['variables_binarias']=sum(v.isBinary() for v in p.variables())
            r['variables_enteras_no_binarias']=sum(v.cat==pulp.LpInteger and not v.isBinary() for v in p.variables())
            r['variables_continuas']=sum(v.cat==pulp.LpContinuous for v in p.variables())
            native=resolver(p,metodo,salida/'solver.log',threads=1,seed=42,limite=limite)
            r['solver']=native;r['segundos_metodo']=native['segundos']
            X=np.full((len(D),len(S),h),np.nan);Y=X.copy()
            for k in x:
                if x[k].value() is not None:X[k]=x[k].value()
                if y[k].value() is not None:Y[k]=y[k].value()
        a=auditar(d,X,Y);r['auditoria']=a;r['factible']=bool(a['factible'])
        r['objetivo_factible']=a.get('objetivo_recalculado') if r['factible'] else None
        r['demanda_pendiente']=a.get('demanda_pendiente')
        if metodo!='Heuristica':
            s=r['solver'];ub=s.get('ub');lb=s.get('lb')
            coincide=ub is not None and a.get('objetivo_recalculado') is not None and abs(ub-a['objetivo_recalculado'])<=1e-5
            r['certificado']=bool(s['certificado'] and r['factible'] and coincide)
            r['inviable_demostrado']=bool(s.get('infeasible'))
            r['estado']=('Optimo certificado numericamente' if r['certificado'] else
                'Inviable demostrado' if r['inviable_demostrado'] else
                'Factible sin certificado' if r['factible'] else 'Sin plan factible validado')
            r['LB']=lb;r['UB']=r['objetivo_factible']
            r['GAP_pct']=100*abs(r['UB']-lb)/max(abs(r['UB']),1e-10) if r['UB'] is not None and lb is not None and math.isfinite(lb) else None
            r['nota_cota']='CBC: la cota no óptima proviene del log y puede estar redondeada.' if metodo=='CBC' else 'Cota nativa del motor.'
            r['tiempo_certificacion_s']=r['segundos_metodo'] if r['certificado'] else None
        # Se conserva también el candidato rechazado, sin denominarlo plan factible.
        if np.isfinite(X).all() and np.isfinite(Y).all():
            records=[dict(producto=d['productos'][i],maquina=d['maquinas'][j],dia=t+1,
                          unidades=float(X[i,j,t]),activacion=float(Y[i,j,t]))
                     for i,j,t in np.ndindex(X.shape) if X[i,j,t]!=0 or Y[i,j,t]!=0]
            pd.DataFrame(records,columns=['producto','maquina','dia','unidades','activacion']).to_csv(salida/'plan.csv',index=False,lineterminator='\n')
            r['plan_sha256']=sha(salida/'plan.csv')
    except Exception as exc:
        r['estado']='Error';r['tipo_error']=type(exc).__name__
        # No serializar entorno ni detalles de licencia.
        r['error']='Revisar dependencias, licencia y registro de ejecución.' if metodo=='Gurobi' else str(exc)
    r['segundos_totales']=time.perf_counter()-inicio
    guardar(salida/'resultado.json',r)
    return r


def ejecutar(instancias, salida, desde=1, hasta=4, limite=600., metodos=None):
    if limite<=0 or not math.isfinite(limite):raise ValueError('Presupuesto inválido')
    carpeta=Path(instancias);salida=Path(salida)
    manifest=pd.read_csv(carpeta/'manifest.csv');metodos=metodos or METODOS
    if not 1<=desde<=hasta<=len(manifest):raise ValueError('Rango fuera del manifiesto')
    if set(metodos)-set(METODOS):raise ValueError('Método desconocido')
    firma=dict(manifest_sha256=sha(carpeta/'manifest.csv'),limite_s=limite,hilos=1,semilla=42,
               warm_start=False,codigo_sha256=codigo())
    protocolo=salida/'protocolo_ejecucion.json'
    if protocolo.exists() and json.loads(protocolo.read_text(encoding='utf-8'))!=firma:
        raise ValueError('La carpeta contiene otro protocolo. Usa una salida nueva.')
    guardar(protocolo,firma)
    for k in range(desde-1,hasta):
        fila=manifest.iloc[k];path=carpeta/fila.archivo
        if sha(path)!=fila.sha256:raise ValueError(f'Hash incorrecto: {fila.id}')
        orden=['Heuristica']+list(list(itertools.permutations(['CBC','HiGHS','Gurobi']))[k%6])
        for metodo in [m for m in orden if m in metodos]:
            out=salida/fila.id/metodo;result=out/'resultado.json'
            if result.exists():
                prev=json.loads(result.read_text(encoding='utf-8'))
                if prev.get('entrada_sha256')!=fila.sha256:raise ValueError('Resultado anterior de otra entrada')
                print(f'{fila.id} {metodo}: ya registrado; no se repite',flush=True);continue
            out.mkdir(parents=True,exist_ok=True)
            print(f'{fila.id} {metodo}: inicio',flush=True)
            # Proceso separado para liberar memoria y evitar compartir estados del solver.
            cmd=[sys.executable,str(Path(__file__).resolve()),'worker','--instancia',str(path.resolve()),
                 '--metodo',metodo,'--salida',str(out.resolve()),'--limite',str(limite)]
            with (out/'ejecucion.log').open('w',encoding='utf-8') as log:
                completed=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=False)
            if not result.exists():
                guardar(result,dict(id=fila.id,metodo=metodo,entrada_sha256=fila.sha256,
                    estado='Interrupcion externa o error de proceso',returncode=completed.returncode,
                    certificado=False,factible=False,limite_s=limite))
            print(f'{fila.id} {metodo}: {json.loads(result.read_text(encoding="utf-8"))["estado"]}',flush=True)


    errores=[]
    for k in range(desde-1,hasta):
        ident=manifest.iloc[k].id
        for metodo in metodos:
            registro=json.loads((salida/ident/metodo/'resultado.json').read_text(encoding='utf-8'))
            if registro['estado'].startswith(('Error','Interrupcion')):
                errores.append(f'{ident}/{metodo}')
    if errores:
        raise RuntimeError('Bloque con errores de ejecución: '+', '.join(errores))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='accion',required=True)
    a=sub.add_parser('lote');a.add_argument('--instancias',required=True);a.add_argument('--salida',required=True)
    a.add_argument('--desde',type=int,default=1);a.add_argument('--hasta',type=int,default=4)
    a.add_argument('--limite',type=float,default=600);a.add_argument('--metodos',nargs='+',choices=METODOS,default=METODOS)
    w=sub.add_parser('worker');w.add_argument('--instancia',required=True);w.add_argument('--metodo',choices=METODOS,required=True)
    w.add_argument('--salida',required=True);w.add_argument('--limite',type=float,required=True)
    args=vars(p.parse_args());accion=args.pop('accion')
    if accion=='worker':worker(**args)
    else:ejecutar(**args)
