"""Vistas de resultados; los registros originales se conservan en la evidencia."""
import io
import json
import pandas as pd

PRINCIPALES = {
    'horizonte_dias':'Días','optimizador':'Solver','repeticion':'Repetición',
    'estado':'Estado','certificado':'Certificado','objetivo_min':'Objetivo (min)',
    'LB_min':'Cota inferior (min)','GAP_pct':'GAP (%)',
    'GAP_abs_min':'Diferencia absoluta (min)','segundos_totales':'Tiempo total (s)',
}
DETALLE = {
    'horizonte_dias':'Días','optimizador':'Solver','repeticion':'Repetición','semilla':'Semilla',
    'referencias':'Referencias','demanda_unidades':'Demanda (unidades)',
    'demanda_cumplida_pct':'Demanda cumplida (%)','produccion_min':'Producción (min)',
    'setup_min':'Preparación (min)','participacion_setup_pct':'Preparación / objetivo (%)',
    'setups_activos':'Preparaciones activas','utilizacion_media_pct':'Utilización media (%)',
    'utilizacion_max_pct':'Utilización máxima (%)','holgura_total_min':'Holgura total (min)',
    'residuo_max':'Residuo máximo','nodos':'Nodos acumulados','variables':'Variables del último modelo',
    'restricciones':'Restricciones del último modelo','version_solver':'Versión del solver',
    'metodo':'Método','warm_start':'Con inicio factible','origen_inicio':'Origen del inicio',
    'error':'Detalle del error',
}


def tabla(df, detalle=False):
    nombres = DETALLE if detalle else PRINCIPALES
    return df.reindex(columns=list(nombres)).rename(columns=nombres)


def indicadores(st, df):
    ok = df[df.certificado.eq(True)]
    cols = st.columns(3)
    cols[0].metric('Óptimos certificados', f'{len(ok)} / {len(df)}')
    cols[1].metric('Tiempo acumulado', f"{df.get('segundos_totales',pd.Series(dtype=float)).sum()/60:.2f} min")
    cols[2].metric('Tasa de certificación del lote', f'{100*len(ok)/len(df):.1f}%')
    st.caption('Tiempo total: preparación, resolución y validación. Una celda vacía significa dato no disponible. GAP cero requiere certificado; la diferencia absoluta conserva el residuo numérico sin ocultarlo.')


def mostrar_planes(st, folder, df):
    ok = df[df.certificado.eq(True)]
    if ok.empty:
        st.info('El plan aparecerá después de una ejecución certificada.')
        return
    labels = [f"{int(r.horizonte_dias)} días · {r.optimizador} · repetición {int(r.repeticion)}" for r in ok.itertuples()]
    selected = st.selectbox('Plan certificado', range(len(labels)), format_func=lambda i:labels[i], key='plan_resultado_v7')
    r = ok.iloc[selected]; h = int(r.horizonte_dias)
    tag = f"{h}d_{r.optimizador}_{int(r.repeticion):02d}"
    path = folder / (tag+'_plan.csv')
    if not path.exists():
        st.warning('El archivo del plan ya no está disponible en esta sesión.')
        return
    if h == 1:
        raw = pd.read_csv(path,index_col=0)
        plan = raw.rename_axis('Referencia').reset_index().melt(id_vars='Referencia',var_name='Máquina',value_name='Unidades')
        plan = plan[plan.Unidades > 0].copy(); plan.insert(0,'Día',1)
    else:
        plan = pd.read_csv(path).rename(columns={'dia':'Día','producto':'Referencia','maquina':'Máquina','unidades':'Unidades'})
        plan = plan[['Día','Referencia','Máquina','Unidades']]
    C = pd.read_csv(folder/f'C_{h}d.csv',index_col=0)
    S = pd.read_csv(folder/f'S_{h}d.csv',index_col=0).iloc[:,0]
    cap = json.loads((folder/'config.json').read_text())['capacidad']
    plan['Producción (min)'] = [row.Unidades*C.loc[row.Referencia,getattr(row,'Máquina')] for row in plan.itertuples(index=False)]
    plan['Preparación (min)'] = plan['Máquina'].map(S)
    plan = plan.sort_values(['Día','Máquina','Referencia'])
    load = plan.groupby(['Día','Máquina'])[['Producción (min)','Preparación (min)']].sum()
    full = pd.MultiIndex.from_product([range(1,h+1),C.columns],names=['Día','Máquina'])
    load = load.reindex(full,fill_value=0)
    load['Carga (min)'] = load.sum(axis=1)
    load['Utilización (%)'] = load['Carga (min)']/cap*100
    load['Holgura (min)'] = cap-load['Carga (min)']
    st.dataframe(plan,hide_index=True,width='stretch')
    st.caption('El modelo asigna cantidades por máquina y día. No determina el orden de fabricación ni las horas de inicio de cada lote.')
    st.dataframe(load.reset_index(),hide_index=True,width='stretch')
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer,engine='openpyxl') as writer:
        plan.to_excel(writer,sheet_name='Plan',index=False)
        load.reset_index().to_excel(writer,sheet_name='Capacidad',index=False)
        tabla(pd.DataFrame([r])).to_excel(writer,sheet_name='Certificacion',index=False)
        for sheet in writer.book:
            sheet.freeze_panes='A2'
            for col in sheet.columns:
                sheet.column_dimensions[col[0].column_letter].width=min(60,max(16,max(len(str(c.value or '')) for c in col)+2))
    st.download_button('Descargar plan y capacidad',buffer.getvalue(),f'plan_{tag}.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
