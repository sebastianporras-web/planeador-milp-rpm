from pathlib import Path
import sys,json
import numpy as np
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from experimento_19.modelo import construir,auditar,heuristica
from experimento_19.ejecutar import worker,guardar
from experimento_19.solver_benchmark import resolver


def datos(h=1):
    return dict(productos=['A','B'],maquinas=['M1','M2'],demanda=[6,6],
        tiempos_min=[[1.,1.3],[1.,3.]],setup_min=[2.,2.],capacidad_min_dia=[12.,20.],horizonte_dias=h)


def test_certificados_contra_enumeracion_independiente(tmp_path):
    valores=[]
    for a in range(7):
        for b in range(7):
            l1=a+b+2*(a>0)+2*(b>0)
            l2=1.3*(6-a)+3*(6-b)+2*(a<6)+2*(b<6)
            if l1<=12 and l2<=20:valores.append(l1+l2)
    d=datos();inst=tmp_path/'i.json';guardar(inst,dict(meta={'id':'T001'},datos=d))
    hashes=[]
    for metodo in ['CBC','HiGHS']:
        r=worker(inst,metodo,tmp_path/metodo,10)
        assert r['certificado'],r
        assert r['objetivo_factible']==pytest.approx(min(valores))
        assert not r['warm_start']
        hashes.append(r['modelo_sha256'])
    assert hashes[0]==hashes[1]


def test_rechaza_warm_start(tmp_path):
    p,x,y=construir(datos());next(iter(x.values())).setInitialValue(1)
    with pytest.raises(ValueError,match='heredadas'):resolver(p,'CBC',tmp_path/'solver.log',limite=10)


def test_inviable_no_certificado(tmp_path):
    d=datos();d['demanda']=[600,600]
    p=tmp_path/'i.json';guardar(p,dict(meta={'id':'T002'},datos=d))
    for metodo in ['CBC','HiGHS']:
        r=worker(p,metodo,tmp_path/metodo,10)
        assert not r['certificado']
        assert not r['factible']
        assert r.get('inviable_demostrado'),r


def test_auditor_detecta_demanda_y_capacidad():
    d=datos();X,Y=heuristica(d);r=auditar(d,X,Y)
    assert r['residuos']['capacidad']<=1e-5
    X[0,0,0]+=100
    r=auditar(d,X,Y)
    assert not r['factible'] and r['residuos']['capacidad']>0 and r['residuos']['demanda']>0


def test_integridad_y_enlace_independientes():
    d=datos();X=np.zeros((2,2,1));Y=X.copy();X[0,0,0]=.5
    r=auditar(d,X,Y)
    assert r['residuos']['integridad']==.5
    assert r['residuos']['enlace']==.5


def test_multidia_demanda_total(tmp_path):
    d=datos(3);p=tmp_path/'i.json';guardar(p,dict(meta={'id':'T003'},datos=d))
    for metodo in ['CBC','HiGHS']:
        r=worker(p,metodo,tmp_path/metodo,10)
        assert r['certificado'],r
        # Dos productos en M1, en días distintos: 12 min de proceso + 4 de setup.
        assert r['objetivo_factible']==pytest.approx(16.)


def test_heuristica_parcial_no_es_plan_factible():
    d=datos();d['demanda']=[600,600];X,Y=heuristica(d);r=auditar(d,X,Y)
    assert not r['factible'] and r['demanda_pendiente']>0
    assert r['residuos']['capacidad']<=1e-5


def test_reporte_no_convierte_ausentes_en_exitos(tmp_path):
    import pandas as pd
    from experimento_19.reportar import reportar
    from experimento_19.ejecutar import sha
    ins=tmp_path/'instancias';ins.mkdir();res=tmp_path/'resultados';res.mkdir()
    pd.DataFrame([dict(id='I001',sha256='fixture',referencias_solicitadas=2,horizonte_dias=1,
        nivel_demanda=1,capacidad='nominal',matriz='publicada',naturaleza='sensibilidad_determinista_exploratoria')]).to_csv(ins/'manifest.csv',index=False)
    guardar(res/'protocolo_ejecucion.json',dict(manifest_sha256=sha(ins/'manifest.csv')))
    guardar(res/'CBC/resultado.json',dict(id='I001',metodo='CBC',entrada_sha256='fixture',
        estado='Factible sin certificado',factible=True,certificado=False,objetivo_factible=18.,segundos_metodo=10.))
    df=reportar(ins,res,tmp_path/'informe')
    assert len(df)==4 and (df.estado=='Ausente').sum()==3
    estado=json.loads((tmp_path/'informe/estado_informe.json').read_text())
    assert not estado['completo']
    perfil=pd.read_csv(tmp_path/'informe/perfil_dolan_more.csv')
    assert perfil.fraccion.eq(0).all()
    # Una copia repetida debe fallar, no seleccionar automáticamente un resultado.
    guardar(res/'duplicado/resultado.json',json.loads((res/'CBC/resultado.json').read_text()))
    with pytest.raises(ValueError,match='repetido'):reportar(ins,res,tmp_path/'informe2')
