"""Interfaz operativa RPM. La prueba numérica reside en los motores auditados."""
import hashlib
import io
from pathlib import Path
import pandas as pd
import streamlit as st
import rpm_core as core
from carga_limpia import cargar
from comparacion_solvers import renderizar

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title='RPM Colombia | Planeación',page_icon='🏭',layout='wide')
st.markdown("""
<style>
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p,
[data-testid="stMetricLabel"] {color: #CBD5E1 !important; opacity: 1 !important;}
input::placeholder, textarea::placeholder {color: #CBD5E1 !important; opacity: 1 !important;}
button:disabled {opacity: 1 !important; color: #CBD5E1 !important; background-color: #334155 !important;}
[data-testid="stSidebar"] a {color: #B9DEFA;}
</style>
""", unsafe_allow_html=True)

st.title('Planeación de producción | RPM Colombia')
st.caption('Asignación de referencias a las máquinas disponibles. Objetivo: minimizar los minutos de producción y preparación, cumpliendo demanda y capacidad.')
st.sidebar.caption('RPM · versión 11')
st.sidebar.header('Datos de entrada')
uploaded = st.sidebar.file_uploader('Cargar Excel',type=['xlsx'],key='entrada_limpia_v7')
options=['Datos del estudio','Mi plantilla completada','Demanda total · horizonte automático']
file_hash=hashlib.sha256(uploaded.getvalue()).hexdigest() if uploaded else ''
if st.session_state.get('archivo_flexible_v10') != file_hash:
    st.session_state['archivo_flexible_v10']=file_hash
    default=options[0]
    if uploaded:
        default=options[1]
        try:
            sheets=set(pd.ExcelFile(io.BytesIO(uploaded.getvalue())).sheet_names)
            if {'Demanda','Maquinas'}<=sheets or {'Referencias','Recursos'}<=sheets:default=options[2]
        except Exception:pass
    st.session_state['modo_flexible_v10']=default
source_mode = st.sidebar.radio('Fuente de datos',options,key='modo_flexible_v10')
st.sidebar.caption('CBC / HiGHS / Gurobi: sin límite interno de tiempo. La plataforma puede interrumpir la sesión o reiniciar el servidor.')
if source_mode==options[2]:
    from operacion_flexible import renderizar as renderizar_flexible
    renderizar_flexible(st,uploaded.getvalue() if uploaded else None)
    st.stop()
if any(j and j['process'].poll() is None for j in [st.session_state.get('flex_search'),st.session_state.get('flex_batch')]):
    st.info('Hay una planificación de demanda total activa. Selecciona Demanda total · horizonte automático para consultar su avance.');st.stop()
st.sidebar.download_button('Plantilla del estudio',(ROOT/'Plantilla_datos_RPM.xlsx').read_bytes(),'Plantilla_datos_RPM.xlsx')
st.sidebar.download_button('Instructivo de carga · PDF',(ROOT/'Instructivo_carga_RPM.pdf').read_bytes(),'Instructivo_carga_RPM.pdf',mime='application/pdf')
cap = st.sidebar.number_input('Capacidad por máquina y día (min)',min_value=1.0,max_value=1440.0,value=1440.0,step=30.0)
st.sidebar.caption('Usa minutos netos disponibles. La capacidad es igual para M1 a M10 y para todos los días del horizonte.')
st.sidebar.caption('CBC / HiGHS / Gurobi: sin límite interno de tiempo. GAP relativo y absoluto solicitados: 0. La plataforma puede interrumpir una sesión o reiniciar el servidor.')
try:
    if source_mode == 'Mi plantilla completada':
        if uploaded is None:
            st.info('Descarga la plantilla, completa tus datos y carga el Excel. No contiene datos de ejemplo ni simulados.')
            st.stop()
        data = uploaded.getvalue()
        instances = cargar(io.BytesIO(data))
        origin = 'Plantilla operativa: demandas explícitas y tiempos aportados por el usuario.'
    else:
        data = (ROOT/'AnexodeDatosxlsx.xlsx').read_bytes()
        daily = core.cargar_datos(io.BytesIO(data))
        extended = core.cargar_datos_extendido(io.BytesIO(data),180)
        cal = core.calibrar_demanda_extendida(daily['demanda'],extended['demanda'])
        instances = {1:(daily['cij'],core.demanda_entera(daily['demanda']),daily['setup']),
                     3:(extended['cij'],core.demanda_entera(cal['demanda_calibrada']*3),extended['setup'])}
        origin = 'Reproducción del estudio: matriz diaria publicada y catálogo extendido histórico; demanda extendida calibrada con 180 días hábiles. Incluye tiempos estimados/simulados del anexo, no exclusivamente mediciones.'
except Exception as exc:
    st.error(str(exc));st.stop()

signature = hashlib.sha256(data+source_mode.encode()).hexdigest()
if st.session_state.get('fuente_v7') != signature:
    st.session_state['fuente_v7'] = signature
    # Ajustar selecciones a los horizontes presentes sin tocar un lote en curso.
    st.session_state['bench_h'] = sorted(instances)
st.caption(origin)
overview = pd.DataFrame([{'Horizonte (días)':h,'Referencias con demanda':len(C),'Demanda (unidades)':int(D.sum()),'Máquinas':len(S)} for h,(C,D,S) in instances.items()])
st.dataframe(overview,hide_index=True,width='stretch')
with st.expander('Revisar datos antes de resolver'):
    for h,(C,D,S) in instances.items():
        st.write(f'**Horizonte de {h} día(s)** · tiempos M1–M10 en min/unidad')
        st.dataframe(pd.concat([D.rename('Demanda (unidades)'),C],axis=1),width='stretch')
    st.dataframe(S.rename('Preparación (min)').to_frame(),width='stretch')
    st.caption('Cij representa tiempo por unidad, no costo monetario. Una preparación se cobra por referencia, máquina y día con producción. El horizonte de tres días cumple demanda total al final, sin fechas de entrega diarias internas.')
st.divider()
C,D,S = next(iter(instances.values()))
renderizar(C,D,S,lambda:io.BytesIO(data),float(cap),source_mode,instancias_preparadas=instances)
st.divider()
st.caption('Los análisis de clustering, sensibilidad y Monte Carlo del anexo permanecen en «Analisis del estudio», en el menú lateral. Las simulaciones se ejecutan solo cuando se solicitan; no forman parte de la plantilla vacía.')
