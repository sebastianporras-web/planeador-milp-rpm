"""Revisa los planes históricos guardados; no ejecuta optimizadores."""
from pathlib import Path
import zipfile,json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
O=Path(__file__).resolve().parent
R=O/'evidencia/historica_extraida'
if not (R/'validacion_rpm_resultados/monte_carlo_escenarios.csv').exists():
 R.mkdir(exist_ok=True)
 with zipfile.ZipFile(O/'evidencia/validacion_historica.zip') as z:z.extractall(R)
R=R/'validacion_rpm_resultados'
P=O/'evidencia/descomprimida'
if not (P/'S_1d.csv').exists():
 P.mkdir(exist_ok=True)
 with zipfile.ZipFile(O/'evidencia/evidencia_optimizadores.zip') as z:z.extractall(P)
C=pd.read_csv(R/'matriz_publicada.csv',index_col=0)
C0=pd.read_csv(P/'C_1d.csv',index_col=0).reindex(index=C.index,columns=C.columns)
assert np.allclose(C,C0,rtol=0,atol=1e-10)
S=pd.read_csv(P/'S_1d.csv',index_col=0).iloc[:,0].reindex(C.columns).to_numpy()
f=pd.read_csv(R/'monte_carlo_escenarios.csv');d=pd.read_csv(R/'monte_carlo_demandas.csv',index_col=0)
assert len(f)==len(d)==1000 and f.escenario.nunique()==1000
rows=[]
for _,r in f.iterrows():
 n=int(r.escenario);z=np.load(R/f'mc_planes/{n:04d}.npz');x=z['X'][:,:,0];y=z['Y'][:,:,0];D=z['D']
 assert np.array_equal(D,d.iloc[n-1].to_numpy())
 U=np.maximum(0,np.minimum(D[:,None],np.floor((1440-S[None,:])/C.to_numpy())))
 loads=(C.to_numpy()*x+S[None,:]*y).sum(axis=0)
 checks={'demanda':float(abs(x.sum(axis=1)-D).max()),'capacidad':float(max(0,(loads-1440).max())), 'enlace':float(max(0,(x-U*y).max())), 'integridad':float(max(abs(x-np.round(x)).max(),abs(y-np.round(y)).max())), 'dominio':float(max(0,-x.min(),-y.min(),y.max()-1)), 'objetivo':float(abs(loads.sum()-r.objective))}
 rows.append(dict(escenario=n,**checks,cumple=max(checks.values())<1e-5))
v=pd.DataFrame(rows);assert v.cumple.all();v.to_csv(O/'tablas/auditoria_planes_monte_carlo.csv',index=False)
a=100*(1-f.objective/f.heuristica_objetivo);b=100*(1-f.lower_bound/f.heuristica_objetivo)
assert np.allclose(a,f.mejora_incumbente_pct) and np.allclose(b,f.mejora_cota_superior_pct)
assert np.allclose(d.sum(axis=1),f.demanda_total)
checks=dict(n=1000,planes_verificados=int(v.cumple.sum()),media=float(a.mean()),mediana=float(a.median()),sd=float(a.std()),min=float(a.min()),max=float(a.max()),cota_media=float(b.mean()),gap_max=float(f.gap_pct.max()),gap_medio=float(f.gap_pct.mean()),demanda_min=int(f.demanda_total.min()),demanda_max=int(f.demanda_total.max()),max_residuos=v.drop(columns=['escenario','cumple']).max().to_dict())
(O/'tablas/auditoria_monte_carlo.json').write_text(json.dumps(checks,indent=2))
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
fig,ax=plt.subplots(figsize=(8,3.6));ax.hist(a,bins=25,color='#315b7c',edgecolor='white');ax.axvline(a.mean(),color='#b65a24',lw=2,label=f'Media: {a.mean():.4f} %');ax.set(xlabel='Reducción frente a la heurística factible (%)',ylabel='Número de escenarios');ax.legend(frameon=False);fig.tight_layout();fig.savefig(O/'figuras/monte_carlo_mejora.pdf');plt.close(fig)
fig,axs=plt.subplots(1,2,figsize=(8,3.5));axs[0].scatter(f.demanda_total,a,s=7,alpha=.35,color='#315b7c');axs[0].set(xlabel='Demanda del escenario (unidades)',ylabel='Mejora del incumbente (%)');axs[1].hist(f.gap_pct,bins=30,color='#b65a24',edgecolor='white');axs[1].set(xlabel='GAP del escenario (%)',ylabel='Número de escenarios');fig.tight_layout();fig.savefig(O/'figuras/monte_carlo_gap.pdf');plt.close(fig)
print(json.dumps(checks,indent=2))
