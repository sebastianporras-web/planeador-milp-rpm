"""Desagregación selectiva exacta para demanda TOTAL, sin precedencias entre días.

Cada maestro es una relajación del modelo diario. Incorporar días para una
máquina elimina sólo soluciones agregadas que no admiten programación diaria.
Un maestro óptimo que se distribuye en todas las máquinas certifica el MILP.
No es una heurística que fije la primera asignación agregada.
"""
import argparse
import hashlib
import json
import math
import platform
import time
from pathlib import Path
import numpy as np
import pandas as pd
import pulp
from solver_config_rpm import resolver


def guardar(path, data):
    def clean(x):
        if isinstance(x, dict): return {str(k):clean(v) for k,v in x.items()}
        if isinstance(x, (list,tuple)): return [clean(v) for v in x]
        if isinstance(x, (float,np.floating)) and not math.isfinite(x): return None
        if isinstance(x,np.generic): return x.item()
        return x
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(clean(data),ensure_ascii=False,indent=2),encoding='utf-8')
    tmp.replace(path)


def cargar(folder):
    folder=Path(folder)
    C=pd.read_csv(folder/'C_3d.csv',index_col=0)
    D=pd.read_csv(folder/'D_3d.csv',index_col=0).iloc[:,0]
    S=pd.read_csv(folder/'S_3d.csv',index_col=0).iloc[:,0]
    plan=pd.read_csv(folder/'plan_inicial_comun_3d.csv')
    return C,D,S,plan


def validar_datos(C,D,S,cap,dias):
    if not C.index.is_unique or not C.columns.is_unique: raise ValueError('Índices duplicados')
    if not C.index.equals(D.index) or not C.columns.equals(S.index): raise ValueError('Índices desalineados')
    if not np.isfinite(C.values).all() or (C.values<=0).any(): raise ValueError('C inválida')
    if not np.isfinite(S.values).all() or (S.values<0).any(): raise ValueError('S inválida')
    if not np.isfinite(D.values).all() or (D.values<0).any() or (D.values!=np.rint(D.values)).any():
        raise ValueError('Demanda debe ser entera no negativa')
    if not math.isfinite(cap) or cap<=0 or dias<1 or int(dias)!=dias: raise ValueError('Capacidad/horizonte inválidos')


def validar_plan(C,D,S,cap,dias,P):
    required={'producto','maquina','dia','unidades'}
    if not required.issubset(P.columns): raise ValueError('Plan incompleto')
    if (not P.producto.isin(C.index).all() or not P.maquina.isin(C.columns).all()
        or not P.dia.isin(range(1,dias+1)).all()): raise ValueError('Plan fuera del dominio')
    q=P.unidades.to_numpy(dtype=float)
    if not np.isfinite(q).all() or (q<=0).any() or (abs(q-np.rint(q))>1e-7).any():
        raise ValueError('Plan con cantidades inválidas')
    P=P.groupby(['producto','maquina','dia'],as_index=False).unidades.sum()
    err=(P.groupby('producto').unidades.sum().reindex(D.index,fill_value=0)-D).abs().max()
    loads={}; obj=0.; linkerr=0.
    for r in P.itertuples():
        c=float(C.loc[r.producto,r.maquina]); s=float(S[r.maquina])
        u=max(0,min(int(D[r.producto]),math.floor((cap-s)/c)))
        linkerr=max(linkerr,float(r.unidades)-u)
        load=c*r.unidades+s; obj+=load
        key=(r.maquina,int(r.dia)); loads[key]=loads.get(key,0)+load
    maxload=max(loads.values(),default=0.)
    ok=err<=1e-7 and maxload<=cap+1e-6 and linkerr<=1e-7
    return dict(factible=bool(ok),objetivo=float(obj),error_demanda=float(err),
                exceso_capacidad=max(0.,maxload-cap),error_enlace=linkerr,
                integridad=True,max_carga=maxload,unidades=int(P.unidades.sum()))


def construir(C,D,S,cap,dias,detalladas,plan=None,dominios=None):
    I=range(len(C)); J=range(len(S)); T=range(dias)
    c=C.to_numpy(); d=D.to_numpy(); s=S.to_numpy()
    U=np.maximum(0,np.minimum(d[:,None],np.floor((cap-s)/c))).astype(int)
    p=pulp.LpProblem('RPM_selectivo',pulp.LpMinimize)
    A={};N={};X={};Y={}
    for i in I:
        for j in J:
            A[i,j]=pulp.LpVariable(f'A_{i}_{j}',0,min(int(d[i]),dias*int(U[i,j])),cat='Integer')
            # Un setup vacío es dominado cuando S>=0; N<=A preserva un óptimo.
            N[i,j]=pulp.LpVariable(f'N_{i}_{j}',0,min(dias,int(d[i])) if U[i,j]>0 else 0,cat='Integer')
            p+=A[i,j]<=int(U[i,j])*N[i,j]
            p+=A[i,j]>=N[i,j]
            # Envolvente entera de A<=U*N, A<=D. No redondea C ni S.
            # D=q*U+r: entre N=q y q+1 la pendiente válida es r.
            u=int(U[i,j]); di=int(d[i])
            if u and di<dias*u:
                q,r=divmod(di,u)
                if r and q:
                    p+=A[i,j]<=r*N[i,j]+q*(u-r),f'enlace_entero_{i}_{j}'
    p+=pulp.lpSum(float(c[i,j])*A[i,j]+float(s[j])*N[i,j] for i in I for j in J)
    for i in I:
        p+=pulp.lpSum(A[i,j] for j in J)==int(d[i])
        maxu=int(U[i].max())
        if maxu:
            p+=pulp.lpSum(N[i,j] for j in J)>=math.ceil(int(d[i])/maxu)
    for j in J:
        p+=pulp.lpSum(float(c[i,j])*A[i,j]+float(s[j])*N[i,j] for i in I)<=dias*cap,f'cap_agregada_{j}'
        if j not in detalladas: continue
        for i in I:
            for t in T:
                X[i,j,t]=pulp.LpVariable(f'X_{i}_{j}_{t}',0,int(U[i,j]),cat='Integer')
                Y[i,j,t]=pulp.LpVariable(f'Y_{i}_{j}_{t}',cat='Binary')
                p+=X[i,j,t]<=int(U[i,j])*Y[i,j,t]
                p+=X[i,j,t]>=Y[i,j,t]
            p+=pulp.lpSum(X[i,j,t] for t in T)==A[i,j]
            p+=pulp.lpSum(Y[i,j,t] for t in T)==N[i,j]
        loads=[pulp.lpSum(float(c[i,j])*X[i,j,t]+float(s[j])*Y[i,j,t] for i in I) for t in T]
        for load in loads: p+=load<=cap
        for t in range(dias-1): p+=loads[t]>=loads[t+1]
    if dominios is not None:
        from poda_lagrangiana import aplicar
        aplicar(p,A,N,X,Y,dominios,dias,detalladas)
    if plan is not None:
        vals={(i,j,t):0 for i in I for j in J for t in T}
        imap={v:i for i,v in enumerate(C.index)};jmap={v:j for j,v in enumerate(C.columns)}
        for r in plan.itertuples(): vals[imap[r.producto],jmap[r.maquina],int(r.dia)-1]+=int(r.unidades)
        for j in J:
            order=sorted(T,key=lambda t:-sum(c[i,j]*vals[i,j,t]+s[j]*(vals[i,j,t]>0) for i in I))
            for i in I:
                A[i,j].setInitialValue(sum(vals[i,j,t] for t in T))
                N[i,j].setInitialValue(sum(vals[i,j,t]>0 for t in T))
                if j in detalladas:
                    for t,old in enumerate(order):
                        X[i,j,t].setInitialValue(vals[i,j,old]); Y[i,j,t].setInitialValue(int(vals[i,j,old]>0))
    return p,A,N,X,Y,U


def empaquetar(C,S,cap,dias,j,a,n,U):
    active=[i for i in range(len(C)) if a[i]>0];T=range(dias)
    p=pulp.LpProblem('Distribucion_diaria',pulp.LpMinimize)
    x={};y={}
    for i in active:
        for t in T:
            x[i,t]=pulp.LpVariable(f'q_{i}_{t}',0,int(U[i,j]),cat='Integer')
            y[i,t]=pulp.LpVariable(f'b_{i}_{t}',cat='Binary')
            p+=x[i,t]<=int(U[i,j])*y[i,t];p+=x[i,t]>=y[i,t]
        p+=pulp.lpSum(x[i,t] for t in T)==a[i]
        p+=pulp.lpSum(y[i,t] for t in T)==n[i]
    loads=[pulp.lpSum(float(C.iloc[i,j])*x[i,t]+float(S.iloc[j])*y[i,t] for i in active) for t in T]
    for load in loads:p+=load<=cap
    for t in range(dias-1):p+=loads[t]>=loads[t+1]
    # Objetivo positivo constante dado a,n; evita MIPGap indefinido para cero.
    p+=pulp.lpSum(x.values())
    return p,x,active


def ejecutar(C,D,S,plan,folder,solver='HiGHS',modo='selectivo',perfil='base',threads=1,seed=42,cap=1440.,dias=3,budget=0):
    if budget:
        raise ValueError('Esta versión no admite límites internos de tiempo.')
    validar_datos(C,D,S,cap,dias)
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    start=time.perf_counter()
    initial=validar_plan(C,D,S,cap,dias,plan) if plan is not None else {'factible':False,'objetivo':None}
    if plan is not None:
        if not initial['factible']:raise ValueError('Plan inicial no factible')
        plan.to_csv(folder/'mejor_plan_factible.csv',index=False)
    state=dict(certificado=False,estado='En ejecución',solver=solver,modo=modo,
               objetivo=initial['objetivo'],validacion=initial,iteraciones=[],dias=dias,
               referencias=len(C),maquinas=len(S),python=platform.python_version(),
               perfil=perfil,threads_solicitados=threads,semilla=seed,
               presupuesto_ensayo_s=budget,alcance='Modelo original de demanda total')
    guardar(folder/'resultado.json',state)
    detailed=set(range(len(S))) if modo=='completo' else set()
    certified_lb=None
    def solve(p,tag):
        left=None
        r=resolver(p,solver,folder/(tag+'.log'),threads,seed,perfil,left)
        guardar(folder/(tag+'.json'),r)
        return r
    try:
        dominios=None
        if initial['factible']:
            from poda_lagrangiana import calcular
            state['estado']='Preprocesamiento por cotas de costo'
            guardar(folder/'resultado.json',state)
            dominios,poda=calcular(C,D,S,cap,dias,plan,initial['objetivo'],folder)
            state['poda']={k:v for k,v in poda.items() if k!='dominios'}
            guardar(folder/'resultado.json',state)
        for k in range(len(S)+1):
            p,A,N,X,Y,U=construir(C,D,S,cap,dias,detailed,plan,dominios)
            audit=solve(p,f'maestro_{k:02d}')
            step=dict(iteracion=k,maquinas_detalladas=[str(C.columns[j]) for j in sorted(detailed)],maestro=audit)
            state['iteraciones'].append(step);state['segundos']=time.perf_counter()-start
            state['estado']='Maestro sin certificado' if not audit['certificado'] else 'Comprobando distribución'
            # Este UB del maestro NO es un UB del modelo diario.
            if audit.get('lb') is not None: state['cota_inferior']=audit['lb']
            guardar(folder/'resultado.json',state)
            print(json.dumps(dict(iteracion=k,detalladas=step['maquinas_detalladas'],certificado_maestro=audit['certificado'],lb=audit.get('lb')),ensure_ascii=False),flush=True)
            if not audit['certificado']: break
            certified_lb=float(audit['lb'])
            # Certificado por sandwich: LB del maestro <= Z* <= plan validado.
            # Si ya coinciden, no necesitamos redistribuir otra solución agregada.
            if initial['factible'] and abs(initial['objetivo']-certified_lb)<=1e-5:
                state.update(certificado=True,estado='Óptimo certificado numéricamente',
                    objetivo=initial['objetivo'],validacion=initial,
                    diferencia_reconstruccion=abs(initial['objetivo']-certified_lb),
                    gap_certificado_pct=0.,gap_recalculado_pct=max(0.,initial['objetivo']-certified_lb)/max(1e-10,abs(initial['objetivo']))*100,
                    cierre_con_plan_inicial=True,
                    criterio='Maestro del solver seleccionado OPTIMAL con gap nativo cero y cota igual al plan completo validado, dentro de 1e-5 min')
                break
            rows=[];bad=[];step['distribucion']=[]
            for j in range(len(S)):
                if j in detailed:
                    quantities={(i,t):round(X[i,j,t].value()) for i in range(len(C)) for t in range(dias)}
                else:
                    a=[round(A[i,j].value()) for i in range(len(C))];n=[round(N[i,j].value()) for i in range(len(C))]
                    if sum(a)==0:continue
                    pack,x,active=empaquetar(C,S,cap,dias,j,a,n,U)
                    check=solve(pack,f'packing_{k:02d}_{j:02d}')
                    step['distribucion'].append(dict(maquina=str(C.columns[j]),**check))
                    if not check['factible']:
                        # Incluso UNKNOWN permite desagregar: añadimos el modelo exacto,
                        # nunca un corte no demostrado contra la solución candidata.
                        bad.append(j);break
                    quantities={(i,t):round(x[i,t].value()) for i in active for t in range(dias)}
                for (i,t),q in quantities.items():
                    if q>0:rows.append(dict(producto=C.index[i],maquina=C.columns[j],dia=t+1,unidades=q))
            step['maquinas_a_incorporar']=[str(C.columns[j]) for j in bad]
            guardar(folder/'resultado.json',state)
            if not bad:
                candidate=pd.DataFrame(rows,columns=['producto','maquina','dia','unidades'])
                valid=validar_plan(C,D,S,cap,dias,candidate)
                delta=abs(valid['objetivo']-float(audit['ub']))
                state['validacion']=valid;state['diferencia_reconstruccion']=delta
                if not valid['factible'] or delta>1e-5:
                    raise RuntimeError('La reconstrucción no superó la validación independiente')
                candidate.to_csv(folder/'mejor_plan_factible.csv',index=False)
                state.update(certificado=True,estado='Óptimo certificado numéricamente',objetivo=valid['objetivo'],
                             gap_certificado_pct=0.,gap_recalculado_pct=max(0.,valid['objetivo']-float(audit['lb']))/max(1e-10,abs(valid['objetivo']))*100,
                             criterio='Maestro OPTIMAL con gap nativo cero; extensión diaria factible del mismo objetivo dentro de 1e-5 min')
                break
            detailed.update(bad)
        if not state['certificado']:state['estado']='Interrumpida o ensayo sin certificado'
    except Exception as exc:
        state['estado']='Error sin certificado';state['error_tipo']=type(exc).__name__
        # No volcar objetos de entorno/licencia ni cadenas de errores de proveedores.
        raise
    finally:
        state['segundos']=time.perf_counter()-start
        guardar(folder/'resultado.json',state)
        pd.DataFrame([{key:state.get(key) for key in ['solver','modo','estado','certificado','objetivo','cota_inferior','gap_certificado_pct','gap_recalculado_pct','segundos']}]).to_csv(folder/'resumen.csv',index=False)
    return state


def main():
    a=argparse.ArgumentParser()
    a.add_argument('--datos',type=Path,default=Path('datos_rpm'))
    a.add_argument('--salida',type=Path,default=Path('resultados_rpm_v3'))
    a.add_argument('--solver',choices=['CBC','HiGHS','Gurobi'],default='HiGHS')
    a.add_argument('--modo',choices=['selectivo','completo'],default='selectivo')
    a.add_argument('--perfil',choices=['base','agresivo'],default='base')
    a.add_argument('--threads',type=int,default=1,help='0: CPU disponibles; 1: comparación reproducible')
    a.add_argument('--seed',type=int,default=42)
    a.add_argument('--capacidad',type=float,default=1440)
    a.add_argument('--dias',type=int,default=3)
    args=a.parse_args();C,D,S,plan=cargar(args.datos)
    state=ejecutar(C,D,S,plan,args.salida,args.solver,args.modo,args.perfil,args.threads,args.seed,args.capacidad,args.dias)
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.datos.glob('*.csv')}
    guardar(args.salida/'datos_sha256.json',hashes)
    return 0 if state['certificado'] else 2


if __name__=='__main__':
    raise SystemExit(main())
