"""Tablas auditables y perfiles de desempeño; conserva casos ausentes y fallidos."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from experimento_19.ejecutar import guardar, METODOS, sha


def reportar(instancias,resultados,salida):
    instancias=Path(instancias);salida=Path(salida);salida.mkdir(parents=True,exist_ok=True)
    mf=pd.read_csv(instancias/'manifest.csv');found={};protocolos=[]
    for p in Path(resultados).rglob('protocolo_ejecucion.json'):
        protocolos.append(json.loads(p.read_text(encoding='utf-8')))
    if not protocolos:raise ValueError('No hay protocolo de ejecución.')
    if any(x!=protocolos[0] for x in protocolos):raise ValueError('Resultados de protocolos distintos; no combinar.')
    if protocolos[0]['manifest_sha256']!=sha(instancias/'manifest.csv'):raise ValueError('El manifiesto no corresponde a las ejecuciones.')
    for p in Path(resultados).rglob('resultado.json'):
        r=json.loads(p.read_text(encoding='utf-8'));key=(r['id'],r['metodo'])
        if key in found:raise ValueError(f'Resultado repetido {key}; no seleccionar el más favorable.')
        if r['id'] not in set(mf.id) or r['metodo'] not in METODOS:raise ValueError('Resultado fuera del diseño')
        expected=mf.set_index('id').loc[r['id'],'sha256']
        if r.get('entrada_sha256')!=expected:raise ValueError('Entrada de otra versión')
        found[key]=r
    rows=[]
    for cell in mf.to_dict('records'):
        hash_modelos=set()
        for metodo in METODOS:
            r=found.get((cell['id'],metodo),{})
            if r.get('modelo_sha256'):hash_modelos.add(r['modelo_sha256'])
            rows.append(dict(id=cell['id'],metodo=metodo,n=cell['referencias_solicitadas'],
                h=cell['horizonte_dias'],demanda_nivel=cell['nivel_demanda'],capacidad=cell['capacidad'],matriz=cell['matriz'],
                estado=r.get('estado','Ausente'),factible=r.get('factible',False),certificado=r.get('certificado',False),
                inviabilidad=r.get('inviable_demostrado',False),objetivo=r.get('objetivo_factible'),
                pendiente=r.get('demanda_pendiente'),LB=r.get('LB'),GAP_pct=r.get('GAP_pct'),
                segundos=r.get('segundos_metodo'),segundos_totales=r.get('segundos_totales'),
                tiempo_certificacion_s=r.get('tiempo_certificacion_s')))
        if len(hash_modelos)>1:raise ValueError(f'Modelos diferentes entre motores en {cell["id"]}')
    df=pd.DataFrame(rows)
    for col in ['objetivo','pendiente','LB','GAP_pct','segundos','segundos_totales','tiempo_certificacion_s']:
        df[col]=pd.to_numeric(df[col],errors='raise').astype(float)
    for ident,g in df.groupby('id'):
        if g.inviabilidad.any() and g.factible.any():raise ValueError(f'Conflicto entre factibilidad e inviabilidad: {ident}')
        z=g.loc[g.certificado,'objetivo'].dropna()
        if len(z)>1 and z.max()-z.min()>1e-5:raise ValueError(f'Óptimos certificados incompatibles: {ident}')
    completo=bool((df.estado!='Ausente').all())
    valido=bool(completo and not df.estado.str.contains('Error|Interrupcion',case=False).any())
    df.to_csv(salida/'resultados_por_instancia.csv',index=False,lineterminator='\n')
    milp=df[df.metodo!='Heuristica']
    resumen=milp.groupby('metodo').agg(programadas=('id','size'),certificadas=('certificado','sum'),
        factibles=('factible','sum'),inviables_demostradas=('inviabilidad','sum'),
        tiempo_certificado_mediana_s=('tiempo_certificacion_s','median'),GAP_max_pct=('GAP_pct','max')).reset_index()
    resumen['proporcion_certificada']=resumen.certificadas/resumen.programadas
    resumen.to_csv(salida/'resumen_motores.csv',index=False,lineterminator='\n')
    for factores in [['n'],['h'],['demanda_nivel'],['capacidad'],['matriz'],['n','h']]:
        a=milp.groupby(['metodo']+factores).agg(programadas=('id','size'),certificadas=('certificado','sum'),
            tiempo_certificado_mediana_s=('tiempo_certificacion_s','median'),GAP_mediana_pct=('GAP_pct','median')).reset_index()
        a['proporcion_certificada']=a.certificadas/a.programadas
        a.to_csv(salida/('por_'+'_'.join(factores)+'.csv'),index=False,lineterminator='\n')
    h=df[df.metodo=='Heuristica'][['id','factible','objetivo','pendiente']].rename(columns={'factible':'heuristica_factible','objetivo':'objetivo_heuristica','pendiente':'pendiente_heuristica'})
    comp=milp.merge(h,on='id');comp['mejora_pct']=np.nan
    ok=comp.factible & comp.heuristica_factible & comp.objetivo_heuristica.gt(0)
    comp.loc[ok,'mejora_pct']=100*(comp.loc[ok,'objetivo_heuristica']-comp.loc[ok,'objetivo'])/comp.loc[ok,'objetivo_heuristica']
    comp['base_comparacion']=np.where(comp.certificado,'Optimo certificado','Incumbente; no optimo probado')
    comp.loc[~ok,'base_comparacion']='No comparable: falta plan completo o referencia positiva'
    comp.to_csv(salida/'comparacion_heuristica.csv',index=False,lineterminator='\n')
    stats=[]
    for (metodo,tipo),g in comp.groupby(['metodo','base_comparacion']):
        values=g.mejora_pct.dropna()
        if not len(values):continue
        # Remuestreo por bloques demanda × tamaño × horizonte; preserva las cuatro variantes.
        grupos={k:v.mejora_pct.dropna().to_numpy() for k,v in g.groupby(['demanda_nivel','n','h'])}
        blocks=list(grupos.values());rng=np.random.default_rng(19042);means=[]
        for _ in range(1000):
            sample=np.concatenate([blocks[k] for k in rng.integers(0,len(blocks),len(blocks))])
            if len(sample):means.append(float(sample.mean()))
        stats.append(dict(metodo=metodo,base=tipo,n=len(values),media=values.mean(),mediana=values.median(),
            q05=values.quantile(.05),q25=values.quantile(.25),q75=values.quantile(.75),q95=values.quantile(.95),
            minimo=values.min(),maximo=values.max(),IC95_condicional_low=np.quantile(means,.025),IC95_condicional_high=np.quantile(means,.975)))
    pd.DataFrame(stats).to_csv(salida/'distribucion_mejoras.csv',index=False,lineterminator='\n')
    comp.loc[comp.mejora_pct.le(0)|~comp.heuristica_factible|~comp.factible].to_csv(salida/'casos_sin_ventaja_o_sin_comparacion.csv',index=False,lineterminator='\n')
    # Excluir inviabilidad demostrada del perfil de óptimos; mantenerla en tasas globales.
    excluded=set(milp.loc[milp.inviabilidad,'id']);ids=[i for i in mf.id if i not in excluded]
    ratios=milp.pivot(index='id',columns='metodo',values='tiempo_certificacion_s').reindex(ids)
    ratios=ratios.clip(lower=1e-9)
    ratios=ratios.div(ratios.min(axis=1),axis=0).fillna(np.inf)
    perfil=[]
    for tau in np.geomspace(1,100,120):
        for metodo in ['CBC','HiGHS','Gurobi']:
            perfil.append(dict(tau=tau,metodo=metodo,fraccion=float((ratios[metodo]<=tau).mean()) if len(ids) else None,denominador=len(ids)))
    pf=pd.DataFrame(perfil);pf.to_csv(salida/'perfil_dolan_more.csv',index=False,lineterminator='\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(7,4))
    for metodo,g in pf.groupby('metodo'):ax.step(g.tau,g.fraccion,where='post',label=metodo)
    ax.set(xscale='log',ylim=(0,1.03),xlabel='Factor respecto al menor tiempo certificado',ylabel='Fracción de instancias',title='Perfil de desempeño'+(' — parcial' if not valido else ''))
    ax.legend();ax.grid(alpha=.2);fig.tight_layout();fig.savefig(salida/'perfil_desempeno.png',dpi=180);plt.close(fig)
    guardar(salida/'estado_informe.json',dict(instancias=len(mf),ejecuciones_esperadas=len(df),
        ejecuciones_presentes=len(found),completo=completo,sin_errores_y_completo=valido,
        origen='sensibilidad determinista' if 'exploratoria' in mf.naturaleza.iloc[0] else 'bloques de demanda observada',
        IC='Bootstrap por bloques, condicionado al diseño y comparaciones válidas; no inferencia sobre toda la planta.',
        perfil_denominador=len(ids),perfil_inviables_excluidos=sorted(excluded),
        nota='Ausentes y no certificados tienen razón infinita; no se convierten en éxitos.'))
    print(f'Registros presentes: {len(found)}/{len(df)}. Informe completo sin errores: {valido}')
    return df

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ['instancias','resultados','salida']:p.add_argument('--'+k,required=True)
    reportar(**vars(p.parse_args()))
