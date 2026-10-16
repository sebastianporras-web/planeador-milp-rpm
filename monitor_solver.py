"""Cotas parciales, cancelación del lote propio y planes iniciales comunes."""
from pathlib import Path
import math
import os
import re
import signal
import subprocess
import time
import pandas as pd

NUM=r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'

def progreso(path, solver):
    path=Path(path)
    if not path.exists():
        import json
        statepath=path.parent/(path.stem+'_selectivo')/'corrida'/'resultado.json'
        if not statepath.exists():return {}
        try: state=json.loads(statepath.read_text(encoding='utf-8'))
        except (OSError,ValueError):return {}
        lb=state.get('cota_inferior');ub=state.get('objetivo')
        # Sólo LB del maestro: su incumbente puede no admitir reparto diario.
        masters=sorted(statepath.parent.glob('maestro_*.log'))
        updated=statepath.stat().st_mtime
        if masters:
            partial=progreso(masters[-1],solver)
            current=partial.get('LB_progreso_min')
            if current is not None:lb=max(lb,current) if lb is not None else current
            updated=max(updated,partial.get('registro_actualizado_epoch',updated))
        return {'LB_progreso_min':lb,'UB_progreso_min':ub,
                'GAP_progreso_pct':max(0,ub-lb)/abs(ub)*100 if lb is not None and ub not in (None,0) else None,
                'fase_selectiva':state.get('estado'),'registro_actualizado_epoch':updated}

    with path.open('rb') as f:
        f.seek(max(0,path.stat().st_size-128000));text=f.read().decode(errors='replace')
    lb=ub=None
    if solver=='CBC':
        for line in text.splitlines():
            pair=re.search(rf'({NUM}) best solution, best possible ({NUM})',line)
            inc=re.search(rf'Integer solution of ({NUM})',line)
            root=re.search(rf'At root node,.*changed objective from {NUM} to ({NUM})',line)
            if pair:ub,lb=map(float,pair.groups())
            elif inc:ub=float(inc.group(1))
            elif root:lb=float(root.group(1))
    else:
        for line in text.splitlines():
            match=re.match(r'^\s*(?:[A-Za-z]\s+)?\d+\s+\d+\s+\d+\s+[\d.]+%\s+(\S+)\s+(\S+)\s+(?:[\d.]+%|inf)',line)
            if match:
                try:lb,ub=map(float,match.groups())
                except ValueError:pass
    def finite(v):return v if v is not None and math.isfinite(v) and abs(v)<1e40 else None
    lb,ub=finite(lb),finite(ub)
    gap=100*abs(ub-lb)/abs(ub) if lb is not None and ub not in (None,0) else None
    return {'LB_progreso_min':lb,'UB_progreso_min':ub,'GAP_progreso_pct':gap,
            'registro_actualizado_epoch':path.stat().st_mtime}

def cancelar(job):
    """Solo mata el grupo creado para este lote; espera antes de editar su estado."""
    proc=job['process']
    if proc.poll() is not None:return False
    if os.name=='nt':
        subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],check=False,capture_output=True)
    else:
        try:os.killpg(proc.pid,signal.SIGTERM)
        except ProcessLookupError:pass
    try:proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        if os.name!='nt':
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        else:proc.kill()
        proc.wait(timeout=2)
    # También elimina un hijo CBC que no haya terminado al salir el padre.
    if os.name!='nt':
        try:os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass
    return True

def plan_comun(C,D,S,h,cap):
    import rpm_core as core
    from soluciones_guardadas import validar_plan
    if h==1:
        plan=core.politica_empirica(C,D,S,cap)['asignacion']
    else:
        historical=Path(__file__).resolve().parent/'plan_inicial_3d.csv'
        if h==3 and historical.exists():
            plan=pd.read_csv(historical)
            if validar_plan(plan,C,D,S,h,cap):return plan,'Plan de referencia factible obtenido con HiGHS; certificación nueva por el solver seleccionado'
        # Heurística determinista: productos por demanda y máquinas por tiempo.
        left={(t,j):float(cap) for t in range(1,h+1) for j in core.MACHINES};rows=[]
        for i in D.sort_values(ascending=False).index:
            pending=int(D[i])
            for j in C.loc[i].sort_values().index:
                for t in range(1,h+1):
                    q=min(pending,max(0,math.floor((left[t,j]-S[j])/C.loc[i,j])))
                    if q>0:
                        rows.append({'producto':i,'maquina':j,'dia':t,'unidades':q})
                        left[t,j]-=q*C.loc[i,j]+S[j];pending-=q
                    if pending==0:break
                if pending==0:break
        plan=pd.DataFrame(rows,columns=['producto','maquina','dia','unidades'])
    if not validar_plan(plan,C,D,S,h,cap):
        raise ValueError(f'No se encontró un plan inicial factible para {h} día(s). Desactiva el inicio común para resolver desde cero.')
    return plan,'Heurística determinista factible'
