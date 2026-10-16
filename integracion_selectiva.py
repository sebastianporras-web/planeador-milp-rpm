"""Adaptador del motor certificado al contrato de resultados de Streamlit."""
import os
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd


def resolver(C,D,S,dias,cap,plan_inicial=None):
    import rpm_core as core
    from optimizar_rpm import ejecutar
    context=core.RUN_CONTEXT.get()
    solver=context.get('solver',os.environ.get('RPM_SOLVER','HiGHS'))
    parent=Path(context.get('log_dir',os.environ.get('RPM_LOG_DIR',tempfile.gettempdir())))
    parent.mkdir(parents=True,exist_ok=True)
    # ejecutar exige un directorio todavía inexistente.
    tag=context.get('run_id',os.environ.get('RPM_RUN_ID','plan'))
    root=parent/(tag+'_selectivo');root.mkdir(parents=True,exist_ok=False);folder=root/'corrida'
    state=ejecutar(C,D,S,plan_inicial,folder,solver=solver,cap=float(cap),dias=int(dias),
                   seed=int(os.environ.get('RPM_SEED','42')),threads=1)
    if not state['certificado']:raise RuntimeError('El modelo selectivo no certificó el plan completo')
    plan=pd.read_csv(folder/'mejor_plan_factible.csv')
    index=range(1,int(dias)+1)
    prod=pd.DataFrame(0.,index=index,columns=C.columns);setup=prod.copy()
    count=pd.DataFrame(0,index=index,columns=C.columns)
    for r in plan.itertuples():
        prod.loc[r.dia,r.maquina]+=float(C.loc[r.producto,r.maquina])*r.unidades
        setup.loc[r.dia,r.maquina]+=float(S[r.maquina]);count.loc[r.dia,r.maquina]+=1
    util=prod+setup;caps=core._serie_capacidades(cap)
    audits=[it['maestro'] for it in state['iteraciones']]
    audits += [a for it in state['iteraciones'] for a in it.get('distribucion',[])]
    last=state['iteraciones'][-1]['maestro'];first=state['iteraciones'][0]['maestro']
    audit=dict(lower_bound=state['cota_inferior'],upper_bound=state['objetivo'],gap_pct=0.,
        proven_optimal=True,termination_known=True,solver=solver,elapsed_s=state['segundos'],
        solver_version=last['version'],nodes=sum(a.get('nodos') or 0 for a in audits),
        variables=last['variables'],constraints=last['restricciones'],
        max_residual=max(a['residual_max'] for a in audits if a.get('factible')),
        metodo='Desagregación selectiva + poda lagrangiana' if state.get('poda',{}).get('aplicada') else 'Desagregación selectiva exacta',segundos_fases_solver=sum(a['segundos'] for a in audits),
        fase_agregada=dict(elapsed_s=first['segundos'],lower_bound=first['lb'],nodes=first.get('nodos')),
        iteraciones=len(state['iteraciones']),evidencia=str(folder),certificado_selectivo=state)
    core.ULTIMA_AUDITORIA=audit
    return dict(estado='Optimal',estado_presentacion='Óptimo certificado',factible_incumbente=True,
        gap_objetivo_pct=0.,gap_objetivo_alcanzado=False,gap_certificado=True,gap_pct=0.,
        lower_bound=state['cota_inferior'],upper_bound=state['objetivo'],
        solver_termination=dict(stopped_on_time=False,stopped_on_gap=False,proven_optimal=True),
        valor_objetivo=state['objetivo'],plan=plan,utilizacion_dia_maquina=util,
        tiempo_produccion_dia_maquina=prod,tiempo_setup_dia_maquina=setup,
        holgura_dia_maquina=cap-util,setups_dia_maquina=count,dias=int(dias),
        capacidad_min=caps,cap_minutos=float(cap),
        residuos=dict(demanda_max=state['validacion']['error_demanda'],capacidad_max=state['validacion']['exceso_capacidad']))
