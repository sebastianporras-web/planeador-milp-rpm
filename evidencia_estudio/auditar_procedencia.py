from pathlib import Path
import ast,math,hashlib,json
import numpy as np,pandas as pd
O=Path(__file__).resolve().parent
P=O/'evidencia/descomprimida';R=O/'fuentes_verificadas'
if not (P/'C_1d.csv').exists():
 import zipfile
 P.mkdir(exist_ok=True)
 with zipfile.ZipFile(O/'evidencia/evidencia_optimizadores.zip') as z:z.extractall(P)
names={'_cargar_setup','cargar_datos','cargar_datos_extendido','calibrar_demanda_extendida','demanda_entera','_validar_demanda_entera','_serie_capacidades','politica_empirica'}
tree=ast.parse((R/'rpm_core.py').read_text());mod=ast.Module(body=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in names],type_ignores=[])
g=dict(pd=pd,np=np,math=math,MACHINES=[f'M{i}' for i in range(1,11)],CAP_MINUTOS_DIA=1440,TOL=1e-6)
exec(compile(mod,'funciones_verificadas','exec'),g)
data=g['cargar_datos'](O/'evidencia/AnexodeDatosxlsx.xlsx');ext=g['cargar_datos_extendido'](O/'evidencia/AnexodeDatosxlsx.xlsx');cal=g['calibrar_demanda_extendida'](data['demanda'],ext['demanda'])
D1=g['demanda_entera'](data['demanda']);D3=g['demanda_entera'](cal['demanda_calibrada'],3)
checks={}
for h,C,D,S in [(1,data['cij'],D1,data['setup']),(3,ext['cij'],D3,ext['setup'])]:
 cc=pd.read_csv(P/f'C_{h}d.csv',index_col=0);dd=pd.read_csv(P/f'D_{h}d.csv',index_col=0).iloc[:,0];ss=pd.read_csv(P/f'S_{h}d.csv',index_col=0).iloc[:,0]
 checks[str(h)]={'C_error':float(abs(C.reindex_like(cc)-cc).to_numpy().max()),'D_error':float(abs(D.reindex(dd.index)-dd).max()),'S_error':float(abs(S.reindex(ss.index)-ss).max()),'unidades':int(D.sum())}
 assert max(checks[str(h)][x] for x in ['C_error','D_error','S_error'])<1e-10
heur=g['politica_empirica'](data['cij'],D1,data['setup']);X=heur['asignacion'];Y=(X>0).astype(int);C=data['cij'];S=data['setup'];Z=(C*X+Y*S).sum(axis=1)
opt=pd.read_csv(P/'1d_CBC_01_plan.csv',index_col=0).reindex_like(C);Yopt=pd.read_csv(P/'1d_CBC_01_preparaciones.csv',index_col=0).reindex_like(C);Zo=(C*opt+Yopt*S).sum(axis=1)
comp=pd.DataFrame({'demanda':D1,'carga_heuristica':Z,'carga_milp':Zo,'diferencia':Z-Zo})
for label,A in [('heuristica',X),('milp',opt)]:comp['asignacion_'+label]=['; '.join(f'{j}: {int(q)}' for j,q in row.items() if q>0) for _,row in A.iterrows()]
comp.sort_values('diferencia',ascending=False).to_csv(O/'tablas/comparacion_asignaciones.csv')
report={'matrices_reconstruidas':checks,'factor_calibracion':cal['factor_sesgo'],'referencias_comunes':cal['n_referencias_comunes'],'demanda_diaria_sin_redondear':float(data['demanda'].sum()),'demanda_calibrada_200':float(cal['demanda_calibrada'].sum()),'heuristica_objetivo':heur['valor_objetivo'],'faltantes_heuristica':int(heur['demanda_incumplida'].sum()),'diferencia_total':float(comp.diferencia.sum())}
(O/'tablas/auditoria_procedencia.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));print(comp.sort_values('diferencia',ascending=False).head(4).to_string())
