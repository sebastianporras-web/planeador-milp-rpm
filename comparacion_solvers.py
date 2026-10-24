"""Experimento secuencial aislado: dos instancias, hasta tres solvers, diez semillas."""
from pathlib import Path
import hashlib
import io
import json
import math
import os
import platform
import signal
import subprocess
import sys
import tempfile
import time
import zipfile
import pandas as pd
from monitor_solver import progreso, cancelar, plan_comun

ROOT = Path(__file__).resolve().parent

def guardar(path, obj):
    # Nunca exportar Infinity/NaN como si fueran observaciones.
    def limpiar(x):
        if isinstance(x, dict): return {k: limpiar(v) for k, v in x.items()}
        if isinstance(x, list): return [limpiar(v) for v in x]
        if isinstance(x, float) and not math.isfinite(x): return None
        return x
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(limpiar(obj), ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)

def empacar(C, D, S):
    # JSON estándar conserva la representación round-trip del float64.
    def encode(v):
        return json.dumps({'index':v.index.tolist(), 'columns':v.columns.tolist(), 'data':v.to_numpy().tolist()}) if isinstance(v,pd.DataFrame) else json.dumps({'index':v.index.tolist(),'name':v.name,'data':v.tolist()})
    return {'C':encode(C),'D':encode(D),'S':encode(S)}

def desempacar(data):
    c,d,s=(json.loads(data[k]) for k in ['C','D','S'])
    return (pd.DataFrame(c['data'],index=c['index'],columns=c['columns']),
            pd.Series(d['data'],index=d['index'],name=d.get('name')),
            pd.Series(s['data'],index=s['index'],name=s.get('name')))


def programa(instancias, repeticiones=10, solvers=("CBC","HiGHS")):
    # Termina todos los casos diarios antes de iniciar los de tres días.
    return [{'horizonte_dias':int(h),'repeticion':rep,'semilla':41+rep,
             'optimizador':solver,'estado':'Pendiente','certificado':False}
            for h in sorted(instancias,key=int) for rep in range(1,repeticiones+1)
            for solver in (list(solvers) if rep%2 else list(reversed(solvers)))]


def ejecutar(carpeta):
    import pulp
    import highspy
    import rpm_core as core
    from cbc_actual import identidad
    carpeta = Path(carpeta)
    cfg = json.loads((carpeta/'config.json').read_text())
    datos = {int(h): desempacar(d) for h, d in cfg['instancias'].items()}
    meta = dict(cfg, version_app='9', cpu_logicas=os.cpu_count(), tolerancia_validacion=1e-5, python=sys.version, sistema=platform.platform(), cpu=platform.processor(),
                pulp=pulp.__version__, highs=highspy.Highs().version(), cbc=identidad(), hilos=1,
                limite_tiempo=None, gap_relativo=0, gap_absoluto=0, warm_start=cfg.get("warm_start",False),
                codigo_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in [ROOT/n for n in ['rpm_core.py','comparacion_solvers.py','integracion_selectiva.py','optimizar_rpm.py','solver_config_rpm.py','cbc_actual.py','poda_lagrangiana.py','carga_limpia.py','presentacion_resultados.py','gurobi_rpm.py','validacion_tecnica.py']]},
                criterio='Estado óptimo, GAP solicitado cero y residuo máximo <= 1e-5; tolerancias numéricas.',
                orden='Primero horizonte diario completo, luego tres días; alternado por repetición; semillas no equivalen a trayectorias aleatorias idénticas.')
    if 'Gurobi' in cfg['solvers']:
        import gurobipy as gp
        meta['gurobi']='.'.join(map(str,gp.gurobi.version()))
    guardar(carpeta/'protocolo.json', meta)
    for h, (C,D,S) in datos.items():
        C.to_csv(carpeta/f'C_{h}d.csv'); D.to_csv(carpeta/f'D_{h}d.csv'); S.to_csv(carpeta/f'S_{h}d.csv')
    starts={int(h):pd.read_json(io.StringIO(v),orient='split') for h,v in cfg.get('planes_iniciales',{}).items()}
    for h,plan in starts.items():plan.to_csv(carpeta/f'plan_inicial_comun_{h}d.csv',index=(h==1))
    rows = json.loads((carpeta/'estado.json').read_text())
    for i, row in enumerate(rows):
        if row['estado'] != 'Pendiente': continue
        if (carpeta/'detener').exists(): break
        h = row['horizonte_dias']; C,D,S = datos[h]
        tag = f"{h}d_{row['optimizador']}_{row['repeticion']:02d}"
        os.environ.update(RPM_SOLVER=row['optimizador'], RPM_SEED=str(row['semilla']),
                          RPM_RUN_ID=tag, RPM_LOG_DIR=str(carpeta/'logs'))
        row.update(estado='En ejecución', referencias=len(C), demanda_unidades=int(D.sum()),
                   inicio_epoch=time.time(),warm_start=(h in starts),log=f'logs/{tag}.log',
                   inicio_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
        guardar(carpeta/'estado.json', rows)
        core.ULTIMA_AUDITORIA = {}
        inicio = time.perf_counter()
        try:
            res = (core.resolver_asignacion(C,D,S,cfg['capacidad'],plan_inicial=starts.get(h)) if h == 1 else
                   core.resolver_multidia(C,D,S,h,cap_minutos=cfg['capacidad'],plan_inicial=starts.get(h)))
            audit = core.ULTIMA_AUDITORIA
            # Conservar también planes rechazados para diagnosticar la validación.
            if h == 1:
                res['asignacion'].to_csv(carpeta/f'{tag}_plan.csv')
                res['setups'].to_csv(carpeta/f'{tag}_preparaciones.csv')
            else:
                res['plan'].to_csv(carpeta/f'{tag}_plan.csv',index=False)
            from validacion_tecnica import verificar
            validation=verificar(C,D,S,h,cfg['capacidad'],res)
            audit['validacion_plan']=validation
            row.update({k:v for k,v in validation.items() if k not in ('alcance','criterio_demanda')})
            guardar(carpeta/f'{tag}_validacion.json',validation)
            if not validation['plan_verificado']:
                raise RuntimeError('El plan no superó la validación independiente. Revisa los residuos de validación.')
            native_residual=float(audit.get('max_residual',float('inf')))
            lb=float(audit.get('lower_bound',float('nan'))); ub=float(audit.get('upper_bound',float('nan')))
            if not all(math.isfinite(v) for v in (native_residual,lb,ub)) or abs(ub-lb)>1e-5 or abs(ub-res['valor_objetivo'])>1e-5:
                raise RuntimeError('Cotas ausentes, no finitas o incompatibles con la certificación del plan.')
            if not res.get('gap_certificado') or not audit.get('proven_optimal') or audit.get('max_residual', float('inf')) > 1e-5:
                raise RuntimeError('La ejecución no satisface el criterio de certificación.')
            row.update(estado='Óptimo certificado', certificado=True,
                       objetivo_min=res['valor_objetivo'], LB_min=audit['lower_bound'],
                       UB_min=audit['upper_bound'], GAP_pct=audit['gap_pct'],
                       GAP_abs_min=abs(audit['upper_bound']-audit['lower_bound']))
            if h == 1:
                prod=res['tiempo_produccion_min']; setup=res['tiempo_setup_min']
                util=res['utilizacion_min']; ns=res['n_setups']
            else:
                prod=res['tiempo_produccion_dia_maquina']; setup=res['tiempo_setup_dia_maquina']
                util=res['utilizacion_dia_maquina']; ns=res['setups_dia_maquina']
            import numpy as np
            row.update(produccion_min=float(np.asarray(prod).sum()), setup_min=float(np.asarray(setup).sum()),
                       setups_activos=int(np.asarray(ns).sum()),
                       utilizacion_media_pct=float(np.asarray(util).mean()/cfg['capacidad']*100),
                       utilizacion_max_pct=float(np.asarray(util).max()/cfg['capacidad']*100),
                       holgura_total_min=float(h*len(S)*cfg['capacidad']-np.asarray(util).sum()),
                       participacion_setup_pct=float(np.asarray(setup).sum()/res['valor_objetivo']*100) if res['valor_objetivo'] else None,
                       origen_inicio=cfg.get('origen_inicial',{}).get(str(h),'Sin inicio'))
        except Exception as exc:
            row.update(estado='Sin certificado / error', error=str(exc), certificado=False)
        audit = core.ULTIMA_AUDITORIA
        plan_path=carpeta/f'{tag}_plan.csv'
        if plan_path.exists():
            row['plan_sha256']=hashlib.sha256(plan_path.read_bytes()).hexdigest()
        row.update(segundos_totales=time.perf_counter()-inicio,
                   segundos_solver=audit.get('segundos_fases_solver',audit.get('elapsed_s')), residuo_max=audit.get('max_residual'),
                   nodos=audit.get('nodes'), variables=audit.get('variables'), restricciones=audit.get('constraints'),
                   version_solver=audit.get('solver_version'),metodo=audit.get('metodo','MILP diario'),
                   iteraciones_selectivas=audit.get('iteraciones'))
        fase = audit.get('fase_agregada', {})
        row.update(segundos_fase_agregada=fase.get('elapsed_s'),
                   segundos_modelo_completo=audit.get('segundos_modelo_completo'),
                   cota_agregada_min=fase.get('lower_bound'),
                   nodos_fase_agregada=fase.get('nodes'))
        guardar(carpeta/f'{tag}_auditoria.json', audit)
        guardar(carpeta/'estado.json', rows)
    (carpeta/'finalizado').touch()

def resumen(df):
    keys=['horizonte_dias','optimizador']
    base=df.groupby(keys).agg(programadas=('estado','size'), certificadas=('certificado','sum')).reset_index()
    ok=df.loc[df.certificado.eq(True)]
    if not ok.empty:
        stats=ok.groupby(keys).agg(objetivo_min=('objetivo_min','min'), objetivo_max=('objetivo_min','max'),
            tiempo_media_s=('segundos_totales','mean'), tiempo_mediana_s=('segundos_totales','median'),
            tiempo_sd_s=('segundos_totales','std'), tiempo_min_s=('segundos_totales','min'),
            tiempo_max_s=('segundos_totales','max')).reset_index()
        base=base.merge(stats,on=keys,how='left')
        base['CV_tiempo_pct']=100*base.tiempo_sd_s/base.tiempo_media_s
    base['avance_certificado_pct']=100*base.certificadas/base.programadas
    return base

def pares(df):
    from itertools import combinations
    ok=df.loc[df.certificado.eq(True)]
    if ok.empty: return pd.DataFrame()
    keys=['horizonte_dias','repeticion','semilla']
    result=[]
    for a,b in combinations(sorted(ok.optimizador.unique()),2):
        joined=ok[ok.optimizador.eq(a)].merge(ok[ok.optimizador.eq(b)],on=keys,suffixes=('_A','_B'))
        if joined.empty: continue
        out=joined[keys].copy()
        out['optimizador_A']=a; out['optimizador_B']=b
        out['diferencia_objetivo_min']=joined.objetivo_min_A-joined.objetivo_min_B
        out['coinciden_objetivos']=out.diferencia_objetivo_min.abs() <= 1e-5
        out['razon_tiempo_A_B']=joined.segundos_totales_A/joined.segundos_totales_B.replace(0,float('nan'))
        result.append(out)
    return pd.concat(result,ignore_index=True) if result else pd.DataFrame()

def renderizar(cij, demanda, setup, fuente, capacidad, modo, instancias_preparadas=None):
    import streamlit as st
    import plotly.express as px
    import rpm_core as core
    st.subheader('Planificación y certificación')
    st.caption('Prueba individual o lote experimental. Cada ejecución resuelve el modelo de nuevo, sin caché.')
    disponibles=sorted(instancias_preparadas) if instancias_preparadas is not None else [1,3]
    if 'bench_h' in st.session_state and any(h not in disponibles for h in st.session_state['bench_h']):
        st.session_state['bench_h']=[h for h in st.session_state['bench_h'] if h in disponibles]
    hsel=st.multiselect('Horizontes (días)', disponibles, default=None if 'bench_h' in st.session_state else disponibles, key='bench_h')
    from gurobi_rpm import disponibles as solvers_disponibles, entorno_worker
    opciones=solvers_disponibles()
    if 'Gurobi' not in opciones:
        st.caption('Gurobi se habilita al instalar gurobipy y configurar los tres Secrets WLS. CBC y HiGHS siguen disponibles.')
    if 'bench_solvers' in st.session_state and any(v not in opciones for v in st.session_state['bench_solvers']):
        st.session_state['bench_solvers']=[v for v in st.session_state['bench_solvers'] if v in opciones]
    solvers=st.multiselect('Optimizadores', opciones,default=['HiGHS'],key='bench_solvers')
    reps=st.number_input('Repeticiones por optimizador y horizonte',1,10,1,key='bench_reps')
    warm=st.checkbox('Usar la misma solución inicial factible en los optimizadores seleccionados',value=True,key='bench_warm')
    st.caption(f'{len(hsel)*len(solvers)*int(reps)} ejecuciones programadas. Si eliges ambos horizontes, el caso diario se completa primero.')
    habiles=180
    if instancias_preparadas is None:
        habiles=st.number_input('Días hábiles para demanda del catálogo extendido',60,300,180,10,key='bench_days')
    st.caption('Versión 9 · CBC, HiGHS y Gurobi sin límite interno de tiempo; GAP relativo y absoluto solicitados: 0.')
    st.caption('Una repetición genera un plan. Diez repeticiones permiten evaluar la estabilidad del tiempo. La comparación no reutiliza certificados previos.')
    with st.expander('Protocolo y lectura académica'):
        st.markdown('''- Según el número de repeticiones, las semillas a partir de 42 cambian la búsqueda, no la demanda. Son repeticiones de dos instancias, no veinte instancias distintas.
- Los solvers reciben el mismo modelo por horizonte, incluida la reducción de simetría en tres días. El orden alterna entre repeticiones.
- La plantilla operativa utiliza las demandas explícitas de cada horizonte. El modo Datos del estudio conserva la instancia diaria y el catálogo extendido histórico calibrado; no son comparables como efecto aislado del horizonte.
- La poda y la desagregación de tres días son comunes a todos los solvers. La poda usa CBC/CLP y programación dinámica; el tiempo total incluye esa preparación.
- Si el plan previo de HiGHS coincide con los datos y es factible, puede servir de inicio común. Cada solver obtiene su propia cota para certificar el óptimo.
- La igualdad del objetivo no exige planes idénticos: pueden existir óptimos alternativos.
- Las estadísticas de tiempo incluyen solo ejecuciones certificadas y muestran cuántas completaron. Un lote incompleto no permite declarar un ganador.
- La razón de tiempos A/B mayor que 1 indica menor tiempo del optimizador B para ese par. Los nodos son descriptivos: cada solver aplica estrategias distintas.
- El tiempo total incluye construcción, preprocesamiento, resolución y validación de cada corrida. Excluye la carga inicial del Excel y la obtención del inicio común anterior al lote.
- La certificación opera con tolerancias numéricas; no equivale a una prueba con aritmética exacta. Un reinicio del servidor puede interrumpir el lote; descarga la evidencia al terminar.''')
        st.latex(r"\operatorname{GAP}_{abs}=|UB-LB|,\qquad \operatorname{GAP}_{rel}(\%)=100\frac{|UB-LB|}{|UB|}")
        st.caption('La expresión relativa supone UB distinto de cero. LB: mejor cota inferior; UB: mejor solución factible. El modelo minimiza minutos de producción y preparación.')
    job=st.session_state.get('rpm_benchmark')
    running=bool(job and job['process'].poll() is None)
    if st.button('Iniciar comparación',disabled=running or not hsel or not solvers,key='bench_start'):
        try:
            inst={}
            if instancias_preparadas is not None:
                inst={str(h):empacar(*instancias_preparadas[h]) for h in hsel}
            else:
                if 1 in hsel: inst['1']=empacar(cij,core.demanda_entera(demanda),setup)
                if 3 in hsel:
                    ext=core.cargar_datos_extendido(fuente(),int(habiles))
                    cal=core.calibrar_demanda_extendida(demanda,ext['demanda'])
                    inst['3']=empacar(ext['cij'],core.demanda_entera(cal['demanda_calibrada']*3),ext['setup'])
            cfg={'instancias':inst,'capacidad':float(capacidad),'matriz_diaria':modo,'dias_habiles':int(habiles),
                 'solvers':solvers,'repeticiones':int(reps),'warm_start':warm,'planes_iniciales':{},'origen_inicial':{}}
            inicio_comun=time.perf_counter()
            if warm:
                for h,data in inst.items():
                    C,D,S=desempacar(data)
                    plan,origen=plan_comun(C,D,S,int(h),float(capacidad))
                    cfg['planes_iniciales'][h]=plan.to_json(orient='split',double_precision=15)
                    cfg['origen_inicial'][h]=origen
            cfg['segundos_inicio_comun']=time.perf_counter()-inicio_comun if warm else 0.
            cfg['datos_sha256']=hashlib.sha256(json.dumps({'instancias':inst,'capacidad':float(capacidad)},sort_keys=True).encode()).hexdigest()
            cfg['config_sha256']=hashlib.sha256(json.dumps(cfg,sort_keys=True).encode()).hexdigest()
            folder=Path(tempfile.mkdtemp(prefix='rpm_benchmark_'))
            guardar(folder/'config.json',cfg); guardar(folder/'estado.json',programa(inst,int(reps),solvers))
            with (folder/'worker.log').open('w') as log:
                proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),str(folder)],
                    stdout=log,stderr=subprocess.STDOUT,env=entorno_worker(),start_new_session=(os.name!='nt'))
            st.session_state['rpm_benchmark']={'folder':str(folder),'process':proc}
            st.rerun()
        except Exception as exc: st.error(str(exc))
    if not job: return
    folder=Path(job['folder']); proc=job['process']
    st.caption('El lote conserva los datos y la capacidad del momento de inicio. Cambiar los controles no modifica un lote existente.')
    c1,c2,c3=st.columns(3)
    if c1.button('Actualizar resultados',key='bench_refresh'): st.rerun()
    if c2.button('Detener después de la ejecución actual',disabled=not running,key='bench_stop'):
        (folder/'detener').touch()
        st.info('Se completará la ejecución actual y se conservarán las restantes como pendientes.')
    if c3.button('Cancelar ejecución ahora',disabled=not running,key='bench_cancel',type='primary'):
        cancelled=cancelar(job)
        rows=json.loads((folder/'estado.json').read_text())
        for row in rows:
            if row['estado']=='En ejecución':
                row.update(progreso(folder/row.get('log',f"logs/{row['horizonte_dias']}d_{row['optimizador']}_{row['repeticion']:02d}.log"),row['optimizador']))
                row.update(estado='Cancelada por el usuario',certificado=False,
                           segundos_hasta_cancelacion=time.time()-row.get('inicio_epoch',time.time()))
        guardar(folder/'estado.json',rows)
        (folder/'cancelado').touch()
        st.rerun()
    rows=json.loads((folder/'estado.json').read_text())
    if proc.poll() is not None:
        for row in rows:
            if row['estado']=='En ejecución': row.update(estado='Interrumpida / error de proceso',certificado=False)
    for row in rows:
        if row['estado']=='En ejecución':
            log=folder/row.get('log',f"logs/{row['horizonte_dias']}d_{row['optimizador']}_{row['repeticion']:02d}.log")
            row.update(progreso(log,row['optimizador']))
            if 'inicio_epoch' in row:row['segundos_transcurridos']=time.time()-row['inicio_epoch']
    df=pd.DataFrame(rows); done=int((~df.estado.isin(['Pendiente','En ejecución'])).sum())
    st.progress(done/len(df),text=f'{done}/{len(df)} terminadas · {int(df.certificado.sum())} óptimos certificados')
    active=df[df.estado.eq('En ejecución')]
    if not active.empty:
        r=active.iloc[0]; st.write(f"En ejecución: {r.optimizador} · {r.horizonte_dias} días · repetición {r.repeticion}. Pulsa Actualizar resultados para consultar el avance.")
        cols=st.columns(4)
        elapsed=r.get('segundos_transcurridos',float('nan'))
        cols[0].metric('Tiempo transcurrido',f'{elapsed/60:.1f} min' if pd.notna(elapsed) else 'N/D')
        for col,key,label in [(cols[1],'UB_progreso_min','Mejor objetivo factible'),(cols[2],'LB_progreso_min','Cota inferior'),(cols[3],'GAP_progreso_pct','GAP aproximado (%)')]:
            v=r.get(key)
            col.metric(label,f'{v:,.4f}' if v is not None and pd.notna(v) else 'N/D')
        st.caption('Cotas del último registro del solver, con precisión limitada. Un GAP redondeado a cero no es certificado. N/D significa que todavía no hay un registro disponible.')
    if proc.poll() is not None and proc.returncode and not (folder/'cancelado').exists():
        st.error('El proceso terminó con error. Descarga la evidencia para revisar worker.log.')
    from presentacion_resultados import tabla, indicadores, mostrar_planes
    indicadores(st,df)
    from validacion_tecnica import mostrar_validacion, tabla_validacion, protocolo_visible
    t1,tv,t2,t3,t4,t5=st.tabs(['Certificación','Validación técnica','Resumen comparativo','Gráficos','Descargas','Planes'])
    with tv:
        mostrar_validacion(st,df,folder)
    with t1:
        st.dataframe(tabla(df),hide_index=True,width="stretch", column_config={
            "Objetivo (min)": st.column_config.NumberColumn(format="%.6f"),
            "Cota inferior (min)": st.column_config.NumberColumn(format="%.6f"),
            "Cota superior (min)": st.column_config.NumberColumn(format="%.6f"),
            "GAP (%)": st.column_config.NumberColumn(format="%.8g"),
            "Diferencia absoluta (min)": st.column_config.NumberColumn(format="%.3e"),
            "Tiempo total (s)": st.column_config.NumberColumn(format="%.2f")})
        with st.expander("Indicadores operativos y detalle técnico"):
            st.dataframe(tabla(df,detalle=True),hide_index=True,width="stretch")
        st.caption('Celdas vacías = dato no disponible; nunca equivalen a GAP cero. Objetivos y cotas en minutos; tiempos de cómputo en segundos.')
    rs=resumen(df); ps=pares(df)
    nombres_resumen={'horizonte_dias':'Días','optimizador':'Solver','programadas':'Programadas','certificadas':'Certificadas','objetivo_min':'Objetivo mínimo (min)','objetivo_max':'Objetivo máximo (min)','tiempo_media_s':'Tiempo medio (s)','tiempo_mediana_s':'Tiempo mediano (s)','tiempo_sd_s':'Desviación del tiempo (s)','tiempo_min_s':'Tiempo mínimo (s)','tiempo_max_s':'Tiempo máximo (s)','CV_tiempo_pct':'CV del tiempo (%)','avance_certificado_pct':'Certificación del lote (%)'}
    nombres_pares={'horizonte_dias':'Días','repeticion':'Repetición','semilla':'Semilla','diferencia_objetivo_min':'Diferencia A - B (min)','coinciden_objetivos':'Objetivos coinciden','optimizador_A':'Optimizador A','optimizador_B':'Optimizador B','razon_tiempo_A_B':'Tiempo A / B'}
    rs=rs.rename(columns=nombres_resumen);ps=ps.rename(columns=nombres_pares)
    with t2:
        if done<len(df) or not bool(df.certificado.all()):
            st.info('Resumen provisional: hay corridas pendientes, interrumpidas o sin certificado. Los tiempos describen únicamente las corridas certificadas.')
        st.caption('Desviación estándar muestral y CV requieren al menos dos corridas certificadas. Los tiempos se comparan dentro del mismo horizonte; las semillas no crean nuevas instancias de demanda.')
        st.dataframe(rs,hide_index=True,width="stretch")
        if not ps.empty: st.dataframe(ps,hide_index=True,width="stretch")
        else: st.info('La comparación por pares aparecerá cuando ambos solvers certifiquen una misma repetición.')
    with t3:
        ok=df[df.certificado.eq(True)]
        if ok.empty: st.info('Los gráficos aparecerán al completar ejecuciones certificadas.')
        else:
            palette={'CBC':'#E5A07D','HiGHS':'#76C9BB','Gurobi':'#AFA5F5'}
            st.plotly_chart(px.box(ok,x='optimizador',y='segundos_totales',color='optimizador',
                facet_col='horizonte_dias',points='all',color_discrete_map=palette,
                title='Dispersión del tiempo hasta certificar optimalidad'),width="stretch")
            st.plotly_chart(px.scatter(ok,x='repeticion',y='objetivo_min',color='optimizador',
                symbol='optimizador',facet_col='horizonte_dias',color_discrete_map=palette,
                title='Consistencia del valor objetivo'),width="stretch")
            st.plotly_chart(px.bar(ok,x='repeticion',y='utilizacion_media_pct',color='optimizador',
                barmode='group',facet_col='horizonte_dias',color_discrete_map=palette,
                title='Utilización media de capacidad por ejecución'),width="stretch")
    with t5:
        mostrar_planes(st,folder,df)
    with t4:
        st.download_button('Descargar tabla CSV',tabla(df).to_csv(index=False).encode('utf-8-sig'),'comparacion_optimizadores.csv','text/csv')
        book=io.BytesIO()
        with pd.ExcelWriter(book,engine='openpyxl') as writer:
            tabla(df).to_excel(writer,sheet_name='Certificacion',index=False)
            tabla(df,detalle=True).to_excel(writer,sheet_name='Detalle',index=False)
            rs.to_excel(writer,sheet_name='Resumen',index=False)
            ps.to_excel(writer,sheet_name='Pares',index=False)
            tabla_validacion(df).to_excel(writer,sheet_name='Validacion',index=False)
            protocolo_visible(folder).to_excel(writer,sheet_name='Protocolo',index=False)
            for sheet in writer.book:
                sheet.freeze_panes='A2'; sheet.auto_filter.ref=sheet.dimensions
                for column in sheet.columns:
                    sheet.column_dimensions[column[0].column_letter].width=min(42,max(16,len(str(column[0].value))+3))
        st.download_button('Descargar Excel comparativo',book.getvalue(),'comparacion_optimizadores.xlsx')
        if True:
            archive=io.BytesIO()
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
                for p in folder.rglob('*'):
                    if p.is_file() and p.suffix != '.tmp' and p.name not in {'comparacion.csv','comparacion.xlsx','certificacion.csv'}:
                        try:z.write(p,p.relative_to(folder))
                        except FileNotFoundError:pass
                z.writestr('comparacion.csv',df.to_csv(index=False))
                z.writestr('certificacion.csv',tabla(df).to_csv(index=False))
                z.writestr('validacion.csv',tabla_validacion(df).to_csv(index=False))
                z.writestr('comparacion.xlsx',book.getvalue())
            st.download_button('Descargar evidencia y registros',archive.getvalue(),'evidencia_optimizadores.zip','application/zip')
        st.caption('La descarga es una instantánea. Durante una ejecución, los registros pueden contener avances posteriores a la tabla.')

if __name__=='__main__': ejecutar(sys.argv[1])
