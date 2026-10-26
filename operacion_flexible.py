"""Interfaz y worker aislado para demanda total. El estudio histórico permanece separado."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
import pandas as pd
from optimizar_rpm import guardar
from carga_flexible import leer,serializar
from motor_horizonte import Datos,buscar,resolver_h,validar
from horizonte_automatico import horizontes_certificacion

ROOT=Path(__file__).resolve().parent

def excel_entrada(datos=None,recursos=None):
    b=io.BytesIO()
    with pd.ExcelWriter(b,engine='openpyxl') as writer:
        if datos is None:
            pd.DataFrame(columns=['ID','Producto','Demanda_total','M1','M2']).to_excel(writer,sheet_name='Referencias',index=False)
            pd.DataFrame({'Maquina':['M1','M2'],'Setup_min':[None,None],'Capacidad_min_dia':[None,None]}).to_excel(writer,sheet_name='Recursos',index=False)
        else:
            R=datos['nombres'].set_index('ID').reindex(datos['C'].index).copy()
            R['Demanda_total']=datos['D'];R=R.join(datos['C']);R.index.name='ID'
            R.reset_index().to_excel(writer,sheet_name='Referencias',index=False)
            recursos.to_excel(writer,sheet_name='Recursos',index=False)
        instructions=pd.DataFrame({'Concepto':['Unidad_tiempos','Ceros','Demanda','Preparaciones','Capacidad','Identificadores'],
                      'Valor':['Minutos','Asignación no habilitada','Total fija; no se multiplica por días',
                               'Minutos por referencia, máquina y día con producción','Minutos netos por máquina y día, constantes en el horizonte',
                               'ID único por pedido o referencia; máquinas coinciden entre hojas']})
        if datos is not None:
            instructions=pd.concat([instructions,pd.DataFrame({'Concepto':['Supuesto']*len(datos['notas']),'Valor':datos['notas']})],ignore_index=True)
        if datos is not None:instructions.to_excel(writer,sheet_name='Instrucciones',index=False)
    return b.getvalue()

def guardar_exportaciones(folder,datos,h,P):
    name_map={r['ID']:r['Producto'] for r in datos.raw['nombres']}
    plan=P.rename(columns={'i':'ID','j':'Maquina','t':'Dia','q':'Unidades'}).copy()
    plan['Produccion_min']=[datos.c[int(r.i),int(r.j)]*r.q for r in P.itertuples()]
    plan['Setup_min']=[datos.s[int(r.j)] for r in P.itertuples()]
    plan.ID=plan.ID.map(dict(enumerate(datos.ids)));plan.Maquina=plan.Maquina.map(dict(enumerate(datos.maquinas)));plan.Dia+=1
    plan['Producto']=plan.ID.map(name_map)
    full=pd.MultiIndex.from_product([range(1,h+1),datos.maquinas],names=['Dia','Maquina'])
    loads=plan.groupby(['Dia','Maquina'])[['Produccion_min','Setup_min']].sum().reindex(full,fill_value=0)
    loads['Carga_min']=loads.sum(axis=1);loads['Capacidad_min']=[datos.cap[datos.maquinas.index(j)] for t,j in full]
    loads['Holgura_min']=loads.Capacidad_min-loads.Carga_min;loads['Utilizacion_pct']=100*loads.Carga_min/loads.Capacidad_min
    for name,frame in [('capacidad.csv',loads.reset_index()),('plan.csv',plan)]:
        temp=folder/(name+'.tmp');frame.to_csv(temp,index=False);temp.replace(folder/name)

def filas_lote(horizontes,solvers,repeticiones):
    return [dict(dias=h,solver=s,repeticion=r,semilla=41+r,estado='Pendiente',optimo_certificado=False,inviabilidad_demostrada=False)
            for h in sorted(set(horizontes)) for r in range(1,repeticiones+1)
            for s in (solvers if r%2 else list(reversed(solvers)))]

def worker(folder):
    folder=Path(folder);cfg=json.loads((folder/'config.json').read_text())
    try:
        x=Datos(cfg['datos'])
        import platform
        meta={k:cfg[k] for k in ['accion','datos_sha256','supuestos_confirmados','max_variables']}
        meta.update(python=platform.python_version(),sistema=platform.platform(),hilos=1,limite_interno_tiempo=None,
                    gap_relativo=0,gap_absoluto=0,tolerancia_validacion=1e-5,
                    criterio='Demanda total fija; capacidad diaria repetida, sin precedencias ni entregas parciales obligatorias.',
                    sha256_codigo={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ['carga_flexible.py','motor_horizonte.py','operacion_flexible.py','solver_config_rpm.py','certificacion_numerica.py']})
        guardar(folder/'protocolo.json',meta)
        if cfg['accion'] in ('buscar','planificar'):
            manual=cfg.get('modo_horizonte')=='Manual'
            guardar(folder/'fase.json',dict(fase='Calculando horizonte y plan inicial'))
            previous = folder/'busqueda'/'busqueda.json'
            state = json.loads(previous.read_text()) if previous.exists() else buscar(x,folder/'busqueda',cfg['solver'],cfg['max_variables'],solo_cotas=manual)
            P=pd.read_csv(folder/'busqueda'/'inicio_comun.csv');guardar_exportaciones(folder/'busqueda',x,state['horizonte_factible'],P)
            if cfg['accion']=='buscar':return
            if not manual and not state.get('minimo_certificado'):
                raise RuntimeError('La búsqueda no demostró el mínimo de días. Se conserva la evidencia, sin etiquetar un horizonte como óptimo.')
            h=int(cfg['dias']) if manual else state['horizonte_minimo']
            rows=filas_lote([h],[cfg['solver']],1);guardar(folder/'corridas.json',rows)
        else:
            P=pd.read_csv(folder/'busqueda'/'inicio_comun.csv');state=json.loads((folder/'busqueda'/'busqueda.json').read_text())
            rows=json.loads((folder/'corridas.json').read_text())
        for r in rows:
            if (folder/'detener').exists():break
            r.update(estado='En ejecución',inicio_epoch=time.time());guardar(folder/'corridas.json',rows)
            t=time.perf_counter();h=r['dias'];tag=f"{h}d_{r['solver']}_{r['repeticion']:02d}";output=folder/tag
            guardar(folder/'fase.json',dict(fase='Optimizando minutos de producción y preparación',dias=h,solver=r['solver'],repeticion=r['repeticion']))
            called=h>=state['inferior']
            if not called:
                output.mkdir(exist_ok=True)
                result=dict(estado='Inviable demostrado por cota',factible=False,certificado=False,
                            criterio='El horizonte es menor que la cota inferior demostrada en la búsqueda.',cota_inferior_dias=state['inferior'])
                guardar(output/'resultado.json',result)
            else:
                start=P if int(P.t.max())<h else None
                result=resolver_h(x,h,output,r['solver'],r['semilla'],True,start,cfg['max_variables'])
                if result['factible']:
                    plan=pd.read_csv(output/'plan_interno.csv');guardar_exportaciones(output,x,h,plan)
                    if h<state['superior']:
                        state.update(superior=h,horizonte_factible=h,validacion_plan=result['validacion'])
                        P=plan;plan.to_csv(folder/'busqueda'/'inicio_comun.csv',index=False)
                        guardar_exportaciones(folder/'busqueda',x,h,plan)
                    if h==state['inferior']:
                        state.update(minimo_certificado=True,horizonte_minimo=h,estado='Horizonte mínimo certificado')
                elif result['estado']=='Inviable demostrado' and h>=state['inferior']:
                    state['inferior']=h+1
                    if state['inferior']==state['superior']:
                        state.update(minimo_certificado=True,horizonte_minimo=state['superior'],estado='Horizonte mínimo certificado')
                state.setdefault('pruebas_adicionales',[]).append(dict(dias=h,estado=result['estado'],ruta=tag))
                guardar(folder/'busqueda'/'busqueda.json',state)
            r.update(estado=result['estado'],optimo_certificado=result['certificado'],
                     inviabilidad_demostrada=result['estado'].startswith('Inviable demostrado'),solver_ejecutado=called,
                     objetivo_min=result.get('objetivo'),LB_min=result.get('LB'),GAP_pct=result.get('GAP_pct'),
                     tiempo_total_s=time.perf_counter()-t,evidencia=tag,
                     validacion=result.get('validacion'),error=result.get('error'))
            for row in rows:
                row.update(horizonte_minimo_dias=state.get('horizonte_minimo') if state.get('minimo_certificado') else None,
                           minimo_dias_demostrado=bool(state.get('minimo_certificado')),
                           es_horizonte_minimo=bool(state.get('minimo_certificado') and row['dias']==state.get('horizonte_minimo')),
                           referencias=len(x.ids),maquinas=len(x.maquinas),demanda_total=int(x.d.sum()),datos_sha256=cfg['datos_sha256'])
            guardar(folder/'corridas.json',rows)
    except Exception as exc:guardar(folder/'error.json',{'error':str(exc),'tipo':type(exc).__name__})
    finally:(folder/'finalizado').touch()

def iniciar(cfg,previous=None):
    from gurobi_rpm import entorno_worker
    folder=Path(tempfile.mkdtemp(prefix='rpm_flexible_'))
    guardar(folder/'config.json',cfg)
    if previous:
        shutil.copytree(previous/'busqueda',folder/'busqueda')
        if cfg['accion']=='comparar':
            rows=filas_lote(cfg['horizontes'],cfg['solvers'],cfg['repeticiones'])
            guardar(folder/'corridas.json',rows)
    with (folder/'worker.log').open('w') as log:
        process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),str(folder)],stdout=log,
                                 stderr=subprocess.STDOUT,env=entorno_worker(),start_new_session=(os.name!='nt'))
    return {'folder':str(folder),'process':process,'datos_sha256':cfg['datos_sha256']}

def descargas(st,folder):
    if not folder.exists():return
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w',zipfile.ZIP_DEFLATED) as z:
        for f in folder.rglob('*'):
            if f.is_file() and f.suffix!='.tmp':
                try:z.write(f,f.relative_to(folder))
                except FileNotFoundError:pass
    st.download_button('Descargar evidencia de demanda total',data.getvalue(),'evidencia_demanda_total.zip','application/zip',key='flex_zip_'+folder.name)
    statepath=folder/'busqueda'/'busqueda.json'
    state=json.loads(statepath.read_text()) if statepath.exists() else {}
    path=folder/'corridas.json';rows=json.loads(path.read_text()) if path.exists() else []
    if rows:
        flat=pd.DataFrame([{**{k:v for k,v in r.items() if k!='validacion'},**(r.get('validacion') or {})} for r in rows])
        buff=io.BytesIO()
        with pd.ExcelWriter(buff,engine='openpyxl') as writer:
            tabla_certificaciones(rows).to_excel(writer,sheet_name='Corridas',index=False)
            flat.to_excel(writer,sheet_name='Auditoria',index=False)
            valid=flat[flat.optimo_certificado.eq(True)]
            if not valid.empty:
                valid.groupby(['dias','solver']).tiempo_total_s.agg(['count','mean','median','std','min','max']).reset_index().to_excel(writer,sheet_name='Tiempos',index=False)
            pd.DataFrame([{k:v for k,v in state.items() if k not in ('pruebas','cota','validacion_plan')}]).to_excel(writer,sheet_name='Horizonte',index=False)
            pd.DataFrame([dict(dias=v['horizonte'],estado=v['estado'],solver=v['solver']) for v in state.get('pruebas',[])]).to_excel(writer,sheet_name='Busqueda',index=False)
            pd.DataFrame({'Concepto':['Demanda','Hilos','Límite temporal','GAP solicitado','Tolerancia','Prueba de un día','Inicio común','Semillas'],
                          'Valor':['Total fija',1,'Sin límite interno',0,1e-5,'Puede descartarse mediante cota; no implica ejecutar el solver',
                                   'Mismo plan factible para todos los optimizadores, cuando cabe en el horizonte','42 en adelante; no cambian demanda']}).to_excel(writer,sheet_name='Protocolo',index=False)
        st.download_button('Descargar tabla del lote flexible',buff.getvalue(),'comparacion_demanda_total.xlsx',key='flex_xlsx_'+folder.name)
    plans=[p for p in folder.glob('*/plan.csv') if (p.parent/'capacidad.csv').exists()]
    if plans:
        selected=st.selectbox('Plan para descargar',plans,format_func=lambda p:p.parent.name,key='flex_plan_'+folder.name)
        buff=io.BytesIO()
        with pd.ExcelWriter(buff,engine='openpyxl') as writer:
            pd.read_csv(selected).to_excel(writer,sheet_name='Plan',index=False)
            pd.read_csv(selected.parent/'capacidad.csv').to_excel(writer,sheet_name='Capacidad',index=False)
            evidence=selected.parent/'resultado.json'
            status=json.loads(evidence.read_text()) if evidence.exists() else dict(estado='Plan factible de búsqueda; costo no certificado',horizonte_factible=state.get('horizonte_factible'))
            config=json.loads((folder/'config.json').read_text())
            summary={k:v for k,v in status.items() if not isinstance(v,(list,dict))}
            summary['datos_sha256']=config['datos_sha256']
            pd.DataFrame([summary]).to_excel(writer,sheet_name='Estado',index=False)
            pd.DataFrame({'Supuestos':config['datos'].get('notas',[])}).to_excel(writer,sheet_name='Supuestos',index=False)
        st.download_button('Descargar plan y capacidad de demanda total',buff.getvalue(),f'plan_{selected.parent.name}.xlsx',key='flex_plan_file_'+folder.name)

def tabla_certificaciones(rows):
    columns={'dias':'Días','solver':'Optimizador','repeticion':'Repetición','estado':'Estado',
             'objetivo_min':'Objetivo (min)','GAP_pct':'GAP (%)','tiempo_total_s':'Tiempo (s)',
             'minimo_dias_demostrado':'Mínimo de días demostrado','horizonte_minimo_dias':'Mínimo (días)',
             'optimo_certificado':'Costo óptimo certificado','es_horizonte_minimo':'Usa horizonte mínimo',
             'solver_ejecutado':'Solver ejecutado','referencias':'Referencias','maquinas':'Máquinas'}
    return pd.DataFrame(rows).reindex(columns=list(columns)).rename(columns=columns)

def panel_plan(st,folder,key):
    import plotly.express as px
    plans=[p for p in folder.glob('*/plan.csv') if (p.parent/'capacidad.csv').exists()]
    if not plans:
        st.info('El plan aparecerá cuando el motor encuentre y valide una solución factible.');return
    # Mostrar primero planes de optimización; conservar el inicio como alternativa explícita.
    plans.sort(key=lambda p:(p.parent.name=='busqueda',p.parent.name))
    def title(p):
        if p.parent.name=='busqueda':return 'Plan inicial factible · costo sin certificar'
        status=json.loads((p.parent/'resultado.json').read_text())
        return f"{status.get('horizonte','')} días · {status.get('solver','')} · {status['estado']} · {p.parent.name.split('_')[-1]}"
    selected=st.selectbox('Resultado mostrado',plans,format_func=title,key='plan_view_'+key)
    plan=pd.read_csv(selected);capacity=pd.read_csv(selected.parent/'capacidad.csv')
    prod=float(plan.Produccion_min.sum());setup=float(plan.Setup_min.sum());available=float(capacity.Capacidad_min.sum())
    c=st.columns(4);c[0].metric('Demanda atendida',f'{int(plan.Unidades.sum()):,}');c[1].metric('Tiempo total (min)',f'{prod+setup:,.2f}')
    c[2].metric('Uso de capacidad',f'{100*(prod+setup)/available:.2f}%');c[3].metric('Preparaciones',len(plan))
    a,b=st.columns(2)
    by_machine=capacity.groupby('Maquina',sort=False)[['Produccion_min','Setup_min','Capacidad_min']].sum().reset_index()
    long=by_machine.melt(id_vars=['Maquina','Capacidad_min'],value_vars=['Produccion_min','Setup_min'],var_name='Componente',value_name='Minutos')
    long.Componente=long.Componente.map({'Produccion_min':'Producción','Setup_min':'Preparación'})
    fig=px.bar(long,x='Maquina',y='Minutos',color='Componente',color_discrete_map={'Producción':'#60A5FA','Preparación':'#FBBF24'},title='Carga por máquina',template='plotly_dark')
    fig.update_layout(margin=dict(l=10,r=10,t=45,b=10),legend_title_text='');a.plotly_chart(fig,width='stretch',key='machine_'+key)
    by_day=capacity.groupby('Dia')[['Carga_min','Capacidad_min']].sum().reset_index();by_day['Utilización (%)']=100*by_day.Carga_min/by_day.Capacidad_min
    fig=px.line(by_day,x='Dia',y='Utilización (%)',title='Uso de capacidad por día',template='plotly_dark',color_discrete_sequence=['#60A5FA'])
    fig.update_layout(margin=dict(l=10,r=10,t=45,b=10),xaxis_title='Día');fig.update_yaxes(range=[0,105]);b.plotly_chart(fig,width='stretch',key='days_'+key)
    c,d=st.columns(2)
    day=c.selectbox('Filtrar día',['Todos']+sorted(plan.Dia.unique().tolist()),key='day_'+key)
    machine=d.selectbox('Filtrar máquina',['Todas']+capacity.Maquina.drop_duplicates().tolist(),key='machine_filter_'+key)
    visible=plan
    if day!='Todos':visible=visible[visible.Dia==day]
    if machine!='Todas':visible=visible[visible.Maquina==machine]
    st.dataframe(visible[['Dia','Maquina','ID','Producto','Unidades','Produccion_min','Setup_min']].rename(columns={'Dia':'Día','Maquina':'Máquina','Produccion_min':'Producción (min)','Setup_min':'Preparación (min)'}),hide_index=True,width='stretch')
    st.caption('Asignación diaria de cantidades. El modelo no calcula una secuencia de trabajos dentro del día.')

def mostrar_job(st,job):
    from monitor_solver import cancelar
    folder=Path(job['folder']);running=job['process'].poll() is None
    left,right=st.columns([3,1])
    left.caption('Proceso activo · actualiza para consultar el avance.' if running else 'Proceso finalizado · consulta el estado de las certificaciones.')
    if right.button('Actualizar',key='refresh_'+folder.name):st.rerun()
    if (folder/'error.json').exists():st.error(json.loads((folder/'error.json').read_text())['error'])
    if (folder/'cancelado').exists():st.warning('Proceso cancelado. Las ejecuciones incompletas no acreditan optimalidad.')
    path=folder/'busqueda'/'busqueda.json';state=json.loads(path.read_text()) if path.exists() else {}
    if state:
        a,b,c=st.columns(3)
        a.metric('Cota inferior (días)',state.get('inferior','—'));b.metric('Plan factible (días)',state.get('horizonte_factible','—'))
        c.metric('Mínimo demostrado',str(state['horizonte_minimo'])+' días' if state.get('minimo_certificado') else 'Pendiente')
        if not state.get('minimo_certificado'):st.caption('El intervalo de días sigue abierto. Un costo óptimo a horizonte fijo no demuestra, por sí solo, que ese horizonte sea mínimo.')
    phase=folder/'fase.json'
    if running and phase.exists():
        phase_data=json.loads(phase.read_text());st.info(phase_data['fase']+(f" · {phase_data['dias']} días · {phase_data['solver']}" if 'dias' in phase_data else ''))
    path=folder/'corridas.json';rows=json.loads(path.read_text()) if path.exists() else []
    if rows and not running:
        for r in rows:
            if r['estado']=='En ejecución':r.update(estado='Interrumpida / sin conclusión',optimo_certificado=False)
            if r['estado']=='Pendiente':r.update(estado='No ejecutada',optimo_certificado=False)
        guardar(path,rows)
    result,cert,evidence=st.tabs(['Plan de producción','Certificaciones','Evidencia y detalles'])
    with result:panel_plan(st,folder,folder.name)
    with cert:
        if rows:
            c=st.columns(3);c[0].metric('Óptimos de costo',sum(bool(r.get('optimo_certificado')) for r in rows));c[1].metric('Inviables demostrados',sum(bool(r.get('inviabilidad_demostrada')) for r in rows));c[2].metric('Casos programados',len(rows))
            st.dataframe(tabla_certificaciones(rows),hide_index=True,width='stretch')
            st.caption('GAP vacío significa que no hay certificado de optimalidad. Un descarte por cota no ejecuta el solver ni constituye una repetición computacional.')
        else:st.info('La tabla aparecerá al resolver el plan. La certificación del horizonte figura arriba.')
    with evidence:
        descargas(st,folder)
        with st.expander('Validaciones y trazabilidad'):
            st.json({k:v for k,v in state.items() if k!='cota'})
            if rows:st.dataframe(pd.DataFrame([dict(dias=r['dias'],solver=r['solver'],**(r.get('validacion') or {})) for r in rows]),hide_index=True,width='stretch')
        if running:
            a,b=st.columns(2)
            if a.button('Cancelar proceso',key='cancel_'+folder.name):cancelar(job);(folder/'cancelado').touch();st.rerun()
            if rows and b.button('Detener después de esta corrida',key='stop_'+folder.name):(folder/'detener').touch();st.info('Se completará la corrida actual.')
    if not running and not (folder/'finalizado').exists() and not (folder/'cancelado').exists():st.warning('El proceso terminó sin cerrar el registro. Lo pendiente no está certificado.')
    return running

def renderizar(st,archivo):
    from gurobi_rpm import disponibles
    st.subheader('Planificar una demanda total')
    st.caption('Carga la demanda, revisa los recursos y calcula el plan. La demanda permanece fija al modificar los días.')
    st.sidebar.download_button('Descargar plantilla limpia',excel_entrada(),'Plantilla_demanda_total.xlsx')
    guide=ROOT/'Guia_operativa_RPM.pdf'
    if guide.exists():st.sidebar.download_button('Guía de uso · PDF',guide.read_bytes(),guide.name,'application/pdf')
    if archivo is None:
        st.info('Carga tu Excel. La app detecta las referencias y las máquinas del archivo.')
        with st.expander('Cómo preparar otra base'):
            st.write('Usa Referencias con ID, Producto, Demanda_total y una columna por máquina. En Recursos incluye una fila por máquina con Setup_min y Capacidad_min_dia. Agrega máquinas en ambas hojas; no necesitas cambiar el código.')
            st.write('También puedes cargar Demanda/Maquinas. Revisa sus unidades y el tratamiento de nombres repetidos.');return
    file_key=hashlib.sha256(archivo).hexdigest()[:12]
    try:prepared={'Referencias','Recursos'}<=set(pd.ExcelFile(io.BytesIO(archivo)).sheet_names)
    except Exception:prepared=False
    unit=st.selectbox('Unidad de tiempos por unidad',['Segundos','Minutos'],index=1 if prepared else 0,key='flex_unit_'+file_key)
    try:
        data=leer(archivo,unit)
        cols=st.columns(3);cols[0].metric('Pedidos / referencias',len(data['D']));cols[1].metric('Máquinas',len(data['C'].columns));cols[2].metric('Demanda total',f"{int(data['D'].sum()):,}")
        with st.expander('Datos y capacidad disponible',expanded=True):
            resources=st.data_editor(data['recursos'],hide_index=True,disabled=['Maquina'],key='flex_resources_'+file_key,width='stretch')
            st.caption('Preparación y capacidad diaria en minutos. Cada máquina puede tener una capacidad distinta.')
        with st.expander('Supuestos de carga y revisión de referencias',expanded=not prepared):
            for note in data['notas']:st.write(note)
            review=data['nombres'].set_index('ID').join(data['D']).join(data['C']);st.dataframe(review,width='stretch')
            st.caption('Tiempos de esta vista en minutos. Cero = asignación no habilitada.')
        payload=serializar(data,resources);Datos(payload)
        st.download_button('Descargar datos revisados',excel_entrada(data,resources),'Base_preparada_demanda_total.xlsx')
    except Exception as exc:st.error(str(exc));return
    signature=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    accepted=st.checkbox('Confirmo las unidades, los datos, los supuestos y la capacidad disponible.',key='flex_accept_'+signature[:16])
    opts=disponibles();a,b=st.columns(2)
    a.info('Horizonte automático: mínimo de días para completar toda la demanda.')
    solver=b.selectbox('Optimizador',opts,index=opts.index('Gurobi') if 'Gurobi' in opts else 0)
    st.caption('Al confirmar la base comienza la búsqueda de días. Después puedes optimizar el costo o ejecutar las repeticiones de certificación.')
    with st.expander('Configuración avanzada y alcance'):
        maxvars=st.number_input('Protección de memoria: variables por modelo',10000,1000000,250000,10000)
        st.caption('GAP relativo y absoluto solicitados: 0. Sin límite interno de tiempo o nodos. Superar la protección de memoria deja una conclusión pendiente. El servidor puede interrumpir el proceso.')
        st.caption('Días equivalentes, capacidad diaria constante por máquina, demanda disponible desde el inicio, sin precedencias ni entregas internas. Las preparaciones se cobran por referencia, máquina y día activo.')
    main=st.session_state.get('flex_search');batch=st.session_state.get('flex_batch')
    historic=st.session_state.get('rpm_benchmark')
    busy=any(j and j['process'].poll() is None for j in [main,batch,historic])
    own_busy=any(j and j['process'].poll() is None for j in [main,batch])
    if historic and historic['process'].poll() is None:st.info('Hay un lote del estudio en ejecución. Finalízalo antes de iniciar otro plan.')
    cfg=dict(datos=payload,datos_sha256=signature,supuestos_confirmados=bool(accepted),max_variables=int(maxvars))
    # Una búsqueda por configuración confirmada, nunca por cada rerun de Streamlit.
    if accepted and not busy and (main is None or main['datos_sha256'] != signature):
        st.session_state['flex_search']=iniciar(dict(cfg,accion='buscar',solver=solver,modo_horizonte='Automático',dias=None))
        st.session_state.pop('flex_batch',None);st.rerun()
    same = bool(main and main['datos_sha256']==signature)
    statefile = Path(main['folder'])/'busqueda'/'busqueda.json' if same else None
    horizon_state = json.loads(statefile.read_text()) if statefile and statefile.exists() else {}
    minimum = horizon_state.get('horizonte_minimo') if horizon_state.get('minimo_certificado') else None
    st.metric('Horizonte mínimo de la demanda cargada', f'{minimum} días' if minimum else 'Calculando' if same and busy else 'Pendiente')
    if same and not busy and minimum is None:
        if st.button('Reintentar búsqueda del horizonte',disabled=not accepted):
            st.session_state['flex_search']=iniciar(dict(cfg,accion='buscar',solver=solver,modo_horizonte='Automático',dias=None));st.rerun()
    if st.button('Calcular plan óptimo',type='primary',disabled=not accepted or busy or minimum is None):
        st.session_state['flex_search']=iniciar(dict(cfg,accion='planificar',solver=solver,modo_horizonte='Automático',dias=None),Path(main['folder']))
        st.session_state.pop('flex_batch',None);st.rerun()
    if main:
        st.divider()
        if main['datos_sha256']!=signature:
            st.warning('Los resultados guardados corresponden a otros datos o capacidades. Calcula un nuevo plan para certificar esta configuración.')
            with st.expander('Consultar ejecución anterior'):mostrar_job(st,main)
            return
        running=mostrar_job(st,main)
        path=Path(main['folder'])/'busqueda'/'busqueda.json'
        if not running and path.exists():
            state=json.loads(path.read_text());h=state.get('horizonte_minimo') if state.get('minimo_certificado') else None
            if h:
                with st.expander('Comparar optimizadores y repetir la validación'):
                    sols=st.multiselect('Optimizadores del lote',opts,default=[solver]);reps=st.number_input('Repeticiones por optimizador y horizonte',1,10,1)
                    horizons=horizontes_certificacion(state);total=len(horizons)*len(sols)*int(reps)
                    st.write(f'Horizontes: {horizons} días · {total} casos programados.')
                    st.caption('La tabla identifica mínimo de días, óptimo de costo y solver ejecutado por separado. Las repeticiones usan la misma demanda; no son bases diferentes.')
                    if st.button('Ejecutar comparación',disabled=busy or not accepted or not sols):
                        st.session_state['flex_batch']=iniciar(dict(cfg,accion='comparar',solvers=sols,repeticiones=int(reps),horizontes=horizons),Path(main['folder']));st.rerun()
    if batch:
        st.divider();st.subheader('Comparación de optimizadores')
        if batch['datos_sha256']==signature:mostrar_job(st,batch)
        else:st.warning('La comparación anterior corresponde a otra configuración.')
    if own_busy:
        # Actualiza el horizonte y habilita las certificaciones al terminar el worker.
        # No inicia nuevas búsquedas ni resuelve modelos desde el temporizador.
        jobs=[j for j in (main,batch) if j]
        def progreso_actual():
            values=[]
            for job in jobs:
                folder=Path(job['folder'])
                values.append(job['process'].poll())
                for name in ('busqueda/busqueda.json','fase.json','corridas.json','error.json'):
                    p=folder/name
                    values.append(p.stat().st_mtime_ns if p.exists() else None)
            return values
        last=progreso_actual()
        @st.fragment(run_every='3s')
        def actualizar_automaticamente():
            if all(j['process'].poll() is not None for j in jobs) or progreso_actual()!=last:
                st.rerun(scope='app')
        actualizar_automaticamente()

if __name__=='__main__':worker(sys.argv[1])
