"""Comprobación independiente del plan entregado, sin alterar el MILP."""
import json
import math
import numpy as np
import pandas as pd

TOL = 1e-5
IDENTIDAD = {'horizonte_dias':'Días','optimizador':'Solver','repeticion':'Repetición','semilla':'Semilla'}
CAMPOS = {
    **IDENTIDAD, 'plan_verificado':'Plan verificado',
    'demanda_ok':'Demanda cumplida', 'capacidad_ok':'Capacidad respetada',
    'enlace_ok':'Enlaces válidos', 'integridad_ok':'Integridad válida',
    'objetivo_ok':'Objetivo reproducido',
    'error_demanda_max':'Error demanda (unidades)',
    'exceso_capacidad_max':'Exceso capacidad (min)',
    'error_enlace_max':'Violación enlace (unidades)',
    'error_integridad_max':'Residuo integridad (unidades)',
    'error_no_negatividad_max':'Violación no negatividad (unidades)',
    'error_objetivo_abs':'Diferencia objetivo (min)',
    'residuo_max':'Residuo nativo del solver',
}

def verificar(C, D, S, h, cap, res):
    """Valida el plan exportable; para 3 días reconstruye Y=1 si X>0.

    El residuo nativo se conserva aparte: no se usa el redondeo del plan
    como sustituto de la comprobación de las variables originales.
    """
    if h == 1:
        X=res['asignacion']; Y=res['setups']
        if not X.index.equals(C.index) or not X.columns.equals(C.columns):
            raise ValueError('El plan diario no coincide con las referencias y máquinas de entrada.')
        if not Y.index.equals(C.index) or not Y.columns.equals(C.columns):
            raise ValueError('La matriz de preparaciones no coincide con los datos.')
        rows=[(1,i,j,float(X.loc[i,j]),float(Y.loc[i,j])) for i in C.index for j in C.columns]
        plan=pd.DataFrame(rows,columns=['dia','producto','maquina','unidades','activacion'])
        origen='Activaciones Y del resultado diario; X e Y exportados tras redondeo del motor.'
    else:
        plan=res['plan'][['dia','producto','maquina','unidades']].copy()
        plan['activacion']=(plan.unidades>0).astype(float)
        origen='Activaciones reconstruidas como Y=1 si X>0 en el plan desagregado.'
    if plan.duplicated(['dia','producto','maquina']).any():
        raise ValueError('El plan contiene asignaciones duplicadas para referencia, máquina y día.')
    if not plan.producto.isin(C.index).all() or not plan.maquina.isin(C.columns).all():
        raise ValueError('El plan contiene referencias o máquinas desconocidas.')
    if not plan.dia.isin(range(1,h+1)).all():
        raise ValueError('El plan contiene días fuera del horizonte.')
    q=plan.unidades.to_numpy(dtype=float); y=plan.activacion.to_numpy(dtype=float)
    if not np.isfinite(q).all() or not np.isfinite(y).all():
        raise ValueError('El plan contiene cantidades no finitas.')
    c=np.array([float(C.loc[i,j]) for i,j in zip(plan.producto,plan.maquina)])
    s=np.array([float(S[j]) for j in plan.maquina])
    d=np.array([float(D[i]) for i in plan.producto])
    u=np.maximum(0,np.minimum(d,np.floor((float(cap)-s)/c)))
    def maximum(a): return float(np.max(a)) if len(a) else 0.
    error_int=max(maximum(abs(q-np.rint(q))), maximum(abs(y-np.rint(y))), maximum(np.maximum(0,y-1)))
    error_neg=max(maximum(np.maximum(0,-q)),maximum(np.maximum(0,-y)))
    error_link=maximum(np.maximum(0,q-u*y))
    delivered=plan.groupby('producto').unidades.sum().reindex(D.index,fill_value=0)
    demand_error=(delivered-D).abs()
    plan['produccion_min']=q*c; plan['preparacion_min']=y*s
    load=plan.groupby(['dia','maquina'])[['produccion_min','preparacion_min']].sum().sum(axis=1)
    error_cap=maximum(np.maximum(0,load.to_numpy()-float(cap)))
    objective=math.fsum(plan.produccion_min)+math.fsum(plan.preparacion_min)
    reported=float(res['valor_objetivo'])
    error_obj=abs(objective-reported) if math.isfinite(reported) else float('inf')
    errors=dict(error_demanda_max=float(demand_error.max()),exceso_capacidad_max=error_cap,
                error_enlace_max=error_link,error_integridad_max=error_int,
                error_no_negatividad_max=error_neg,error_objetivo_abs=error_obj)
    checks=dict(demanda_ok=errors['error_demanda_max']<=TOL,capacidad_ok=error_cap<=TOL,
                enlace_ok=error_link<=TOL,integridad_ok=error_int<=TOL and error_neg<=TOL,
                objetivo_ok=error_obj<=TOL)
    total=float(D.sum())
    covered=float(np.minimum(np.maximum(delivered.to_numpy(),0),D.to_numpy()).sum())
    return dict(**errors,**checks,plan_verificado=bool(all(checks.values())),
                demanda_cumplida_pct=100*covered/total if total>0 else 100.,
                objetivo_recalculado_min=objective,tolerancia_validacion=TOL,
                alcance=origen,criterio_demanda='Igualdad por referencia; el porcentaje de cobertura no sustituye esta igualdad.')

def tabla_validacion(df):
    out=df.reindex(columns=list(CAMPOS)).rename(columns=CAMPOS)
    for key in ['plan_verificado','demanda_ok','capacidad_ok','enlace_ok','integridad_ok','objetivo_ok']:
        out[CAMPOS[key]]=out[CAMPOS[key]].map(lambda v:'N/D' if pd.isna(v) else 'Cumple' if bool(v) else 'No cumple')
    return out

def protocolo_visible(folder):
    path=folder/'protocolo.json'
    if not path.exists(): return pd.DataFrame(columns=['Parámetro','Valor'])
    m=json.loads(path.read_text())
    rows=[('Versión app',m.get('version_app','Anterior a v9')),
          ('Python',m.get('python')),('Sistema',m.get('sistema')),('CPU',m.get('cpu') or 'No disponible'),
          ('CPU lógicas visibles',m.get('cpu_logicas')),('Hilos por solver',m.get('hilos')),
          ('Límite interno de tiempo','Sin límite' if m.get('limite_tiempo') is None else m['limite_tiempo']),
          ('GAP relativo solicitado',m.get('gap_relativo')),('GAP absoluto solicitado',m.get('gap_absoluto')),
          ('Tolerancia de validación',m.get('tolerancia_validacion',TOL)),
          ('Capacidad por máquina y día (min)',m.get('capacidad')),
          ('PuLP',m.get('pulp')),('HiGHS',m.get('highs')),('Gurobi',m.get('gurobi','No utilizado')),
          ('Inicio común solicitado',m.get('warm_start')),
          ('Preparación del inicio común (s)',m.get('segundos_inicio_comun')),
          ('SHA-256 datos y capacidad',m.get('datos_sha256')),
          ('SHA-256 configuración del lote',m.get('config_sha256'))]
    return pd.DataFrame([(k,'N/D' if v is None else str(v)) for k,v in rows],columns=['Parámetro','Valor'])

def mostrar_validacion(st,df,folder):
    numeric=[CAMPOS[k] for k in CAMPOS if k.startswith(('error_','exceso_')) or k=='residuo_max']
    st.dataframe(tabla_validacion(df),hide_index=True,width='stretch',
                 column_config={k:st.column_config.NumberColumn(format='%.3e') for k in numeric})
    st.caption('Comprobación del plan entregado: demanda por referencia, capacidad por máquina y día, X ≤ U·Y, no negatividad, integridad y objetivo recalculado. Tolerancia absoluta: 1e-5 en la unidad de cada prueba. N/D significa no verificado; nunca equivale a cumple.')
    st.caption('En tres días, la validación reconstruye Y=1 cuando X>0. La auditoría nativa conserva por separado los residuos del solver antes del redondeo. El certificado del modelo completo combina cota del maestro y plan factible validado; un maestro óptimo por sí solo no basta.')
    with st.expander('Criterios matemáticos de validación'):
        st.latex(r'U_{ij}=\max\{0,\min[D_i,\lfloor(Cap-S_j)/C_{ij}\rfloor]\}')
        st.latex(r'\max_i|\sum_{j,t}X_{ijt}-D_i|\leq\varepsilon,\quad \max_{j,t}[\sum_i(C_{ij}X_{ijt}+S_jY_{ijt})-Cap]_+\leq\varepsilon')
        st.latex(r'\max_{i,j,t}[X_{ijt}-U_{ij}Y_{ijt}]_+\leq\varepsilon,\quad |Z_{plan}-Z_{reportado}|\leq\varepsilon')
        st.caption('ε = 1e-5; [a]₊ = max(0,a). X representa unidades; Y, activación de preparación. El caso diario tiene t=1. Las comprobaciones numéricas no constituyen aritmética exacta.')
    with st.expander('Entorno y trazabilidad del lote'):
        st.dataframe(protocolo_visible(folder),hide_index=True,width='stretch')
        st.caption('Los registros nativos, hashes del código, datos, preparaciones y planes se conservan en la evidencia ZIP. Los tiempos dependen de la carga del servidor compartido; una repetición no determina superioridad general.')
