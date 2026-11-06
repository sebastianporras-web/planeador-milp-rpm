from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import numpy as np
import pandas as pd
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('gen19', ROOT/'experimento_19/generar_instancias.py')
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)


def historial(path, productos=('A', 'B')):
    # Datos artificiales exclusivos de pruebas; no evidencia experimental.
    d = pd.DataFrame([(str(fecha.date()), producto, 17 + ((k+3)*(j+7) % 137))
         for k, fecha in enumerate(pd.date_range('2020-01-01', periods=30))
         for j, producto in enumerate(productos)], columns=['Fecha','Referencia','Unidades'])
    d.to_csv(path,index=False)
    return d


def test_historico_completo(tmp_path):
    p=tmp_path/'h.csv'; historial(p)
    assert g.leer_historico(p, ['B','A']).shape == (30,2)


@pytest.mark.parametrize('defecto', ['hueco','duplicado','fraccion','fecha','no_finito'])
def test_historico_rechaza_inconsistencia(tmp_path, defecto):
    p=tmp_path/'h.csv'; d=historial(p)
    if defecto=='hueco': d=d.iloc[1:]
    if defecto=='duplicado': d=pd.concat([d,d.iloc[[0]]])
    if defecto=='fraccion': d['Unidades']=d.Unidades.astype(float); d.loc[0,'Unidades']=.5
    if defecto=='fecha': d.loc[0,'Fecha']='sin fecha'
    if defecto=='no_finito': d['Unidades']=d.Unidades.astype(float); d.loc[0,'Unidades']=np.inf
    d.to_csv(p,index=False)
    with pytest.raises(ValueError): g.leer_historico(p,['A','B'])


@pytest.fixture(scope='module')
def factor(tmp_path_factory):
    folder=tmp_path_factory.mktemp('factor')/'salida'
    filas=g.generar(ROOT/'AnexodeDatosxlsx.xlsx',folder,factorial_exploratorio=True)
    return folder,filas


def test_factorial_completo_y_hashes(factor):
    folder,filas=factor
    assert len(filas)==144
    assert len({r['datos_sha256'] for r in filas})==144
    for r in filas:
        assert hashlib.sha256((folder/r['archivo']).read_bytes()).hexdigest()==r['sha256']
    assert pd.DataFrame(filas).groupby(['nivel_demanda','referencias_solicitadas','horizonte_dias']).size().eq(4).all()


def test_demanda_controlada_entre_matriz_y_capacidad(factor):
    folder,filas=factor
    grupos={}
    for r in filas:
        d=json.loads((folder/r['archivo']).read_text(encoding='utf-8'))['datos']
        clave=(r['nivel_demanda'],r['referencias_solicitadas'],r['horizonte_dias'])
        previo=grupos.setdefault(clave,d['demanda'])
        assert d['demanda']==previo
        assert len(d['productos'])==r['referencias_solicitadas']
        assert all(x>=0 and isinstance(x,int) for x in d['demanda'])


def test_reproducibilidad_y_no_sobrescritura(tmp_path,factor):
    folder,filas=factor
    nuevo=tmp_path/'segunda'
    replica=g.generar(ROOT/'AnexodeDatosxlsx.xlsx',nuevo,factorial_exploratorio=True)
    assert [r['sha256'] for r in filas]==[r['sha256'] for r in replica]
    with pytest.raises(ValueError):
        g.generar(ROOT/'AnexodeDatosxlsx.xlsx',nuevo,factorial_exploratorio=True)


def test_bootstrap_empirico_usa_bloques_observados(tmp_path):
    import rpm_core
    b=rpm_core.cargar_datos_extendido(str(ROOT/'AnexodeDatosxlsx.xlsx'))
    p=tmp_path/'historico_prueba.csv'
    historial(p,tuple(b['cij'].index))
    folder=tmp_path/'empirico'
    filas=g.generar(ROOT/'AnexodeDatosxlsx.xlsx',folder,historico=p)
    h=g.leer_historico(p,b['cij'].index.tolist())
    for r in filas:
        d=json.loads((folder/r['archivo']).read_text(encoding='utf-8'))['datos']
        inicio=h.index.get_loc(pd.Timestamp(r['inicio_bloque']))
        esperado=np.floor(h.iloc[inicio:inicio+d['horizonte_dias']][d['productos']].sum().to_numpy()*r['nivel_demanda']+.5).astype(int).tolist()
        assert esperado==d['demanda']
