"""Pruebas con casos artificiales; nunca se incorporan como evidencia del estudio."""
from pathlib import Path
import collections
import hashlib
import json
import sys
from unittest.mock import patch
import numpy as np
import pandas as pd
import pytest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from experimento_19_empirico.generar_instancias import generar,seleccionar_celdas,estratificar
from experimento_19_empirico.ejecutar import worker,guardar
from experimento_19_empirico.solver_benchmark import resolver
from experimento_19.modelo import construir


@pytest.fixture(autouse=True)
def aislar_scheduler_highs():
    # Los tests históricos usan un hilo en este mismo intérprete. El benchmark
    # real crea procesos separados; la prueba debe liberar ese scheduler global.
    import highspy
    highspy.Highs.resetGlobalScheduler(True)
    yield
    highspy.Highs.resetGlobalScheduler(True)


@pytest.fixture(scope='module')
def conjunto(tmp_path_factory):
    out=tmp_path_factory.mktemp('empirico100')/'entradas'
    return out,generar(ROOT/'AnexodeDatosxlsx.xlsx',out)


def test_celdas_cubren_factores_y_marginales():
    c=seleccionar_celdas();assert len(c)==len(set(c))==25
    assert set(x[0] for x in c)=={.8,1.,1.2,1.4}
    assert set(x[1] for x in c)=={99,150,200} and set(x[2] for x in c)=={1,3,5}
    for pos in range(3):
        ns=collections.Counter(x[pos] for x in c).values()
        assert max(ns)-min(ns)<=1


def test_100_problemas_distintos(conjunto):
    root,rows=conjunto
    assert len(rows)==100 and len({x['datos_sha256'] for x in rows})==100
    assert {x['id'] for x in rows}=={f'E{x:03d}' for x in range(1,101)}
    assert all(n==4 for n in collections.Counter(x['bloque_demanda'] for x in rows).values())
    for row in rows:assert hashlib.sha256((root/row['archivo']).read_bytes()).hexdigest()==row['sha256']


def test_trazabilidad_reproduce_cada_unidad(conjunto):
    root,rows=conjunto;trace=pd.read_csv(root/'trazabilidad_demandas.csv')
    base=pd.read_csv(root/'base_empirica.csv').set_index('producto')
    medias=base.groupby('estrato').ventas_semestre.mean()
    for row in rows:
        obj=json.loads((root/row['archivo']).read_text());d=obj['datos']
        tr=trace[trace.bloque_demanda==row['bloque_demanda']].set_index('producto').loc[d['productos']]
        assert (base.loc[tr.donante,'estrato'].to_numpy()==tr.estrato.to_numpy()).all()
        factor=base.loc[tr.donante,'ventas_semestre'].to_numpy()/medias.loc[tr.estrato].to_numpy()
        esperado=np.floor(base.loc[d['productos'],'demanda_diaria_base'].to_numpy()*row['horizonte_dias']*row['nivel_demanda']*factor+.5).astype(int)
        assert esperado.tolist()==d['demanda']


def test_promedio_factores_igual_uno_por_estrato(conjunto):
    root,_=conjunto;base=pd.read_csv(root/'base_empirica.csv')
    assert np.allclose(base.groupby('estrato').factor_empirico.mean(),1.)
    assert not json.loads((root/'protocolo_generacion.json').read_text())['datos_temporales_observados']


def test_demanda_identica_entre_capacidad_matriz(conjunto):
    root,rows=conjunto;seen={}
    for row in rows:
        d=json.loads((root/row['archivo']).read_text())['datos']
        assert seen.setdefault(row['bloque_demanda'],d['demanda'])==d['demanda']


def test_reproducible_sin_sobrescribir(tmp_path,conjunto):
    root,rows=conjunto;other=tmp_path/'otra'
    again=generar(ROOT/'AnexodeDatosxlsx.xlsx',other)
    assert [r['sha256'] for r in again]==[r['sha256'] for r in rows]
    with pytest.raises(ValueError):generar(ROOT/'AnexodeDatosxlsx.xlsx',other)


def datos(h=1):
    return dict(productos=['A','B'],maquinas=['M1','M2'],demanda=[6,6],
        tiempos_min=[[1.,1.3],[1.,3.]],setup_min=[2.,2.],capacidad_min_dia=[12.,20.],horizonte_dias=h)


@pytest.mark.parametrize('metodo',['CBC','HiGHS'])
def test_optimo_vs_enumeracion(tmp_path,metodo):
    values=[]
    for a in range(7):
        for b in range(7):
            l1=a+b+2*(a>0)+2*(b>0);l2=1.3*(6-a)+3*(6-b)+2*(a<6)+2*(b<6)
            if l1<=12 and l2<=20:values.append(l1+l2)
    p=tmp_path/'entrada.json';guardar(p,dict(meta={'id':'PRUEBA'},datos=datos()))
    r=worker(p,metodo,tmp_path/metodo,10,threads=2,perfil='base')
    assert r['certificado'] and r['factible'],r
    assert r['objetivo_factible']==pytest.approx(min(values))
    assert not r['warm_start'] and r['hilos']==2


def test_rechaza_inicio_heredado(tmp_path):
    p,x,y=construir(datos());next(iter(x.values())).setInitialValue(1)
    with pytest.raises(ValueError,match='heredadas'):resolver(p,'CBC',tmp_path/'solver.log',limite=10)


@pytest.mark.parametrize('metodo',['CBC','HiGHS'])
def test_inviabilidad_no_optimo(tmp_path,metodo):
    d=datos();d['demanda']=[600,600]
    p=tmp_path/'entrada.json';guardar(p,dict(meta={'id':'PRUEBA'},datos=d))
    r=worker(p,metodo,tmp_path/metodo,10,threads=2)
    assert r['inviable_demostrado'] and not r['certificado'] and not r['factible'],r


def test_cbc_error_no_se_convierte_en_limite(tmp_path):
    import pulp
    from experimento_19_empirico.cbc_benchmark import CBCBenchmark
    p,x,y=construir(datos());s=CBCBenchmark(msg=False,timeLimit=1,logPath=str(tmp_path/'solver.log'))
    class Fallo:returncode=-11
    with patch('experimento_19_empirico.cbc_benchmark.subprocess.run',return_value=Fallo()):
        with pytest.raises(pulp.PulpSolverError):p.solve(s)
    assert json.loads((tmp_path/'proceso_cbc.json').read_text())['returncode']==-11


def test_cbc_limite_sin_incumbente_normal_se_conserva(tmp_path):
    import pulp
    from experimento_19_empirico.cbc_benchmark import CBCBenchmark
    p,x,y=construir(datos());log=tmp_path/'solver.log'
    s=CBCBenchmark(msg=False,timeLimit=1,logPath=str(log))
    class Limite:returncode=0
    def terminar(*args,**kwargs):
        kwargs['stdout'].write('Result - Stopped on time limit\nNo feasible solution found\nLower bound: 1.0\n')
        return Limite()
    with patch('experimento_19_empirico.cbc_benchmark.subprocess.run',side_effect=terminar):p.solve(s)
    assert p.status==pulp.LpStatusNotSolved
    assert p.sol_status==pulp.LpSolutionNoSolutionFound
    assert all(v.value() is None for v in p.variables())


def test_reporte_parcial_no_declara_cierre(tmp_path,conjunto):
    from experimento_19_empirico.reportar import reportar
    from experimento_19_empirico.ejecutar import ejecutar
    root,_=conjunto;out=tmp_path/'resultados'
    # Presupuesto mínimo solo para probar el flujo; no evidencia final.
    ejecutar(root,out,desde=1,hasta=1,limite=1,threads=2,metodos=['Heuristica'])
    df=reportar(root,out,tmp_path/'informe')
    assert len(df)==400 and (df.estado=='Ausente').sum()==399
    status=json.loads((tmp_path/'informe/estado_informe.json').read_text())
    assert not status['completo'] and not status['sin_errores_y_completo']
    guardar(out/'duplicado/resultado.json',json.loads((out/'E001/Heuristica/resultado.json').read_text()))
    with pytest.raises(ValueError,match='repetido'):reportar(root,out,tmp_path/'informe2')
