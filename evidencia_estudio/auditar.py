from pathlib import Path
import json, hashlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import zipfile
O=Path(__file__).resolve().parent
P=O/'evidencia'/'descomprimida'
if not (P/'comparacion.csv').exists():
    P.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(O/'evidencia'/'evidencia_optimizadores.zip') as z: z.extractall(P)
for sub in ['tablas','figuras']: (O/sub).mkdir(exist_ok=True)
df=pd.read_csv(P/'comparacion.csv')
rows=[]; loads={}; stats={}
for h in [1,3]:
    C=pd.read_csv(P/f'C_{h}d.csv',index_col=0)
    D=pd.read_csv(P/f'D_{h}d.csv',index_col=0).iloc[:,0]
    S=pd.read_csv(P/f'S_{h}d.csv',index_col=0).iloc[:,0]
    U=np.maximum(0,np.minimum(D.to_numpy()[:,None],np.floor((1440-S.to_numpy()[None,:])/C.to_numpy())))
    for solver in ['CBC','HiGHS','Gurobi']:
      for r in range(1,11):
        stem=f'{h}d_{solver}_{r:02d}'
        a=json.loads((P/f'{stem}_auditoria.json').read_text())
        if h==1:
            x=pd.read_csv(P/f'{stem}_plan.csv',index_col=0).reindex(index=C.index,columns=C.columns).to_numpy()[:,:,None]
            y=pd.read_csv(P/f'{stem}_preparaciones.csv',index_col=0).reindex(index=C.index,columns=C.columns).to_numpy()[:,:,None]
        else:
            plan=pd.read_csv(P/f'{stem}_plan.csv')
            x=np.zeros((len(C),len(S),h))
            for _,v in plan.iterrows(): x[C.index.get_loc(v.producto),C.columns.get_loc(v.maquina),int(v.dia)-1]+=v.unidades
            y=(x>0).astype(int)
        load=(C.to_numpy()[:,:,None]*x+S.to_numpy()[None,:,None]*y).sum(axis=0)
        obj=float(load.sum()); LB=a['lower_bound']; UB=a['upper_bound']
        err={'demanda':float(abs(x.sum(axis=(1,2))-D).max()),'capacidad':float(max(0,(load-1440).max())), 'enlace':float(max(0,(x-U[:,:,None]*y).max())), 'integridad':float(max(abs(x-np.round(x)).max(),abs(y-np.round(y)).max())), 'no_negatividad':float(max(0,-x.min(),-y.min())), 'binaria':float(max(0,y.max()-1)), 'objetivo':float(abs(obj-UB)), 'cierre':float(abs(UB-LB))}
        assert max(err.values())<1e-5 and a['proven_optimal'], (stem,err)
        rows.append({'corrida':stem,'objetivo_recalculado':obj,**err,'verificacion':'CUMPLE'})
        if solver=='CBC' and r==1: loads[h]=load
    stats[h]={'demanda':int(D.sum()),'cota_horizonte':float((D*C.min(axis=1)).sum()+len(D)*S.min()),'dimensiones':list(C.shape)}
assert len(rows)==60
pd.DataFrame(rows).to_csv(O/'tablas/auditoria_independiente.csv',index=False)
df.to_csv(O/'tablas/certificaciones_60_corridas.csv',index=False)
summary=df.groupby(['horizonte_dias','optimizador']).agg(n=('certificado','size'),objetivo=('objetivo_min','mean'),media_s=('segundos_totales','mean'),desv_s=('segundos_totales','std'),min_s=('segundos_totales','min'),max_s=('segundos_totales','max'))
summary.to_csv(O/'tablas/resumen_certificaciones.csv')
logs=[]
for f in (P/'logs').rglob('*.log'):
    txt=f.read_text(errors='replace')
    if any(s in txt for s in ['Result - Optimal solution found','Optimal solution found','Model status        : Optimal','Status            Optimal']): logs.append(str(f.relative_to(P)))
stats['auditoria']={'corridas':len(rows),'max_residuos':{k:max(r[k] for r in rows) for k in err},'logs_optimos':len(logs),'logs':logs}
(O/'tablas/resumen_auditoria.json').write_text(json.dumps(stats,indent=2),encoding='utf8')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.labelcolor':'#222222','text.color':'#222222','savefig.bbox':'tight'})
colors=['#233b54','#52858a','#aa7832']
fig,axs=plt.subplots(1,2,figsize=(10,3.7))
for ax,h in zip(axs,[1,3]):
    for k,s in enumerate(['CBC','HiGHS','Gurobi']):
        v=df[(df.horizonte_dias==h)&(df.optimizador==s)].sort_values('repeticion')
        ax.plot(v.repeticion,v.segundos_totales,'o-',label=s,color=colors[k],lw=1.3,ms=4)
    ax.set(xlabel='Repetición',ylabel='Tiempo total (s)',title=f'{h} día'+('s' if h>1 else ''));ax.set_xticks([1,2,4,6,8,10]);ax.grid(axis='y',alpha=.2)
axs[0].legend(frameon=False);fig.tight_layout();fig.savefig(O/'figuras/tiempos.pdf');plt.close(fig)
fig,ax=plt.subplots(figsize=(9,3.4)); x=np.arange(10)
C=pd.read_csv(P/'C_1d.csv',index_col=0);S=pd.read_csv(P/'S_1d.csv',index_col=0).iloc[:,0]
X=pd.read_csv(P/'1d_CBC_01_plan.csv',index_col=0);Y=pd.read_csv(P/'1d_CBC_01_preparaciones.csv',index_col=0)
prod=(C*X).sum();setup=Y.sum()*S
ax.bar(x,prod,color=colors[0],label='Procesamiento');ax.bar(x,setup,bottom=prod,color=colors[2],label='Alistamiento');ax.axhline(1440,color='#777777',ls='--',lw=1,label='Capacidad diaria')
ax.set(xticks=x,xticklabels=C.columns,ylabel='Minutos de carga',ylim=(0,1650));ax.legend(ncol=3,frameon=False,loc='upper center',bbox_to_anchor=(.5,1.2));fig.tight_layout();fig.savefig(O/'figuras/carga_diaria.pdf');plt.close(fig)
pd.DataFrame({'maquina':C.columns,'procesamiento':prod.values,'alistamiento':setup.values,'carga':loads[1][:,0],'ocupacion_pct':loads[1][:,0]/14.4,'activaciones':Y.sum().values}).to_csv(O/'tablas/carga_diaria.csv',index=False)
fig,ax=plt.subplots(figsize=(9,3.5))
for d in range(3): ax.bar(x+(d-1)*.25,loads[3][:,d],width=.25,label=f'Día {d+1}',color=colors[d])
ax.axhline(1440,color='#777',ls='--',lw=1);ax.set(xticks=x,xticklabels=C.columns,ylabel='Carga máquina-día (min)',ylim=(0,1640));ax.legend(ncol=3,frameon=False);fig.tight_layout();fig.savefig(O/'figuras/carga_tres_dias.pdf');plt.close(fig)
pd.DataFrame(loads[3],index=C.columns,columns=['dia1','dia2','dia3']).to_csv(O/'tablas/carga_tres_dias.csv')
D=pd.read_csv(P/'D_1d.csv',index_col=0).iloc[:,0].sort_values(ascending=False)
fig,ax=plt.subplots(figsize=(8.5,3));ax.plot(np.arange(1,len(D)+1),D.cumsum()/D.sum()*100,color=colors[0]);ax.axhline(80,color=colors[2],ls='--');ax.set(xlabel='Referencias acumuladas por demanda descendente',ylabel='Demanda acumulada (%)',xlim=(1,99),ylim=(0,102));ax.grid(alpha=.2);fig.tight_layout();fig.savefig(O/'figuras/pareto.pdf');plt.close(fig)
def fmt(x,n=3): return f'{x:,.{n}f}'.replace(',','X').replace('.',',').replace('X','.')
with (O/'tablas/tabla_resumen.tex').open('w') as f:
 for (h,s),r in summary.iterrows(): f.write(f'{h} & {s} & 10/10 & {fmt(r.media_s)} & {fmt(r.desv_s)} & {fmt(r.min_s)}--{fmt(r.max_s)} \\\\\n')
for h in [1,3]:
 with (O/f'tablas/detalle_{h}d.tex').open('w') as f:
  for _,r in df[df.horizonte_dias==h].sort_values(['optimizador','repeticion']).iterrows():
   f.write(f'{r.optimizador} & {r.repeticion} & {r.semilla} & {fmt(r.LB_min,6)} & {fmt(r.UB_min,6)} & 0 & {fmt(r.segundos_totales)} \\\\\n')
print(summary.to_string()); print(json.dumps({k:v for k,v in stats.items() if k!='auditoria'},indent=2));print('logs optimos',len(logs));print(stats['auditoria']['max_residuos'])
