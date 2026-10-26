import unittest, tempfile, json, math, sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pulp
import numpy as np
import pandas as pd
import rpm_core as core
from solver_config_rpm import resolver
from certificacion_numerica import cierre_numerico, ResolucionNoCertificada

class Revision(unittest.TestCase):
 def setUp(self):
  self.old=core.MACHINES; core.MACHINES=['M1','M2']
  self.C=pd.DataFrame([[1.,1.3],[1.,3.]],index=['A','B'],columns=core.MACHINES)
  self.D=pd.Series([6,6],index=self.C.index);self.S=pd.Series([2.,2.],index=core.MACHINES)
  self.cap=pd.Series([12.,20.],index=core.MACHINES)
  self.temp=tempfile.TemporaryDirectory();self.token=core.RUN_CONTEXT.set({'log_dir':self.temp.name})
 def tearDown(self):
  core.RUN_CONTEXT.reset(self.token);core.MACHINES=self.old;self.temp.cleanup()
 def test_tolerancia_no_oculta_brecha(self):
  self.assertTrue(cierre_numerico(1e-16,100,100+1e-12))
  for args in [(1e-5,100,100.001),(1e-16,1e12,1e12+1),(0,None,1),(float('nan'),1,1),(-1e-9,1,1)]:
   self.assertFalse(cierre_numerico(*args))
 def test_cbc_y_highs_contra_enumeracion(self):
  vals=[]
  for a in range(7):
   for b in range(7):
    l1=a+b+2*(a>0)+2*(b>0)
    l2=1.3*(6-a)+3*(6-b)+2*(a<6)+2*(b<6)
    if l1<=12 and l2<=20:vals.append(l1+l2)
  self.assertAlmostEqual(min(vals),17.8)
  for name in ['CBC','HiGHS']:
   token=core.RUN_CONTEXT.set({'solver':name,'log_dir':self.temp.name})
   try:r=core.resolver_asignacion(self.C,self.D,self.S,self.cap)
   finally:core.RUN_CONTEXT.reset(token)
   self.assertTrue(r['gap_certificado']);self.assertAlmostEqual(r['valor_objetivo'],min(vals))
   self.assertTrue(all(v<=1e-5 for v in r['residuos'].values()))
   self.assertEqual(r['asignacion'].sum(axis=1).to_dict(),self.D.to_dict())
 def test_infactible_registrado_y_siguiente_continua(self):
  r=core.analisis_sensibilidad(self.C,self.D,self.S,self.cap,factores_demanda=[100,1])
  self.assertFalse(r.iloc[0].optimo_certificado)
  self.assertTrue(pd.isna(r.iloc[0].valor_objetivo_min))
  self.assertTrue(r.iloc[1].optimo_certificado)
  records=[json.loads(p.read_text()) for p in Path(self.temp.name).glob('*.json')]
  self.assertEqual(len(records),2)
  self.assertEqual(sum(x['optimo_certificado'] for x in records),1)
 def test_montecarlo_cuenta_no_certificado(self):
  original=core.resolver_asignacion;n=[0]
  def fail_once(*args,**kwargs):
   n[0]+=1
   if n[0]==1:raise ResolucionNoCertificada('prueba',{'gap_pct':.5,'lower_bound':10,'upper_bound':11})
   return original(*args,**kwargs)
  with patch.object(core,'resolver_asignacion',side_effect=fail_once):
   r=core.monte_carlo_demanda(self.C,self.D,self.S,n_escenarios=3,low=1,high=1,cap_minutos=self.cap)
  self.assertEqual(r['resumen']['n_no_certificados'],1)
  self.assertEqual(r['resumen']['n_optimos_certificados'],2)
  self.assertTrue(pd.isna(r['escenarios'].iloc[0]['tiempo_optimo_min']))
 def test_errores_datos_no_se_ocultan(self):
  with patch.object(core,'resolver_asignacion',side_effect=ValueError('dato inválido')):
   with self.assertRaises(ValueError):core._resolver_escenario(self.C,self.D,self.S,self.cap)
 def test_solver_config_cbc_highs(self):
  for name in ['CBC','HiGHS']:
   m=pulp.LpProblem('Test',pulp.LpMinimize);x=pulp.LpVariable('x',lowBound=0,cat='Integer');m+=x;m+=x>=2.4
   r=resolver(m,name,Path(self.temp.name)/(name+'.log'))
   self.assertTrue(r['certificado']);self.assertAlmostEqual(r['ub'],3)
   if name=='CBC':
    from cbc_actual import identidad
    self.assertIn(identidad()['version_distribucion'],r['version'])
 def test_no_limite_silencioso(self):
  with self.assertRaises(ValueError):core.resolver_asignacion(self.C,self.D,self.S,self.cap,tiempo_limite_seg=1)
 def test_cuello_e_imputacion(self):
  r=core.analisis_cuello_de_botella(self.C,self.D,self.S,self.cap)
  self.assertTrue(r.optimo_certificado.all())
  r=core.analisis_sensibilidad_imputacion(self.C,self.C.notna(),self.D,self.S,cap_minutos=self.cap)
  self.assertTrue(r.optimo_certificado.all())
 def test_referencia_json_raiz_y_avisos(self):
  import ast, types
  path=Path(__file__).resolve().parents[1]/'analisis_tesis.py'
  tree=ast.parse(path.read_text())
  fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='cargar_referencia_monte_carlo')
  fn.decorator_list=[]
  alerts=[];ui=types.SimpleNamespace(warning=alerts.append,error=alerts.append)
  ns={'Path':Path,'json':json,'st':ui,'__file__':str(Path(self.temp.name)/'analisis_tesis.py')}
  exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
  self.assertIsNone(ns['cargar_referencia_monte_carlo']());self.assertEqual(len(alerts),1)
  dest=Path(self.temp.name)/'monte_carlo_reference.json'
  dest.write_text('{')
  self.assertIsNone(ns['cargar_referencia_monte_carlo']());self.assertEqual(len(alerts),2)
  data={k:1 for k in ['n','media_pct','mediana_pct','sd_pct','ci95_low_pct','ci95_high_pct','se_pct','min_pct','max_pct','positive_count']}
  data['methodology_note']='Prueba artificial de lectura, no evidencia histórica'
  dest.write_text(json.dumps(data))
  self.assertEqual(ns['cargar_referencia_monte_carlo'](),data)
if __name__=='__main__':unittest.main(verbosity=2)
