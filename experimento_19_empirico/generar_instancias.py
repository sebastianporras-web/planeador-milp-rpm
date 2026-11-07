"""100 problemas sintéticos con remuestreo transversal de ventas observadas.

La dispersión procede de diferencias entre referencias del mismo estrato.
No se estima variabilidad temporal ni se generan registros de ventas ficticios.
"""
from pathlib import Path
import argparse
import hashlib
import itertools
import json
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
SEMILLA=191007
NIVELES=(.8,1.,1.2,1.4)
TAMANOS=(99,150,200)
HORIZONTES=(1,3,5)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def escribir(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes((json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf-8'))


def seleccionar_celdas(semilla=SEMILLA):
    """Fracción predefinida: 24 celdas latinas más una omitida, antes de resolver.

    Cada nivel tiene 6 o 7 celdas; cada tamaño/horizonte, 8 o 9.
    Cada celda se cruza con las cuatro variantes capacidad x matriz: 100 casos.
    """
    rng=np.random.default_rng(np.random.SeedSequence([semilla,1]))
    a=rng.permutation(4);b=rng.permutation(3);c=rng.permutation(3)
    elegidas=[];omitidas=[]
    for i,j,k in itertools.product(range(4),range(3),range(3)):
        celda=(NIVELES[a[i]],TAMANOS[b[j]],HORIZONTES[c[k]])
        (omitidas if k==(i+j)%3 else elegidas).append(celda)
    elegidas.append(omitidas[int(rng.integers(len(omitidas)))])
    return sorted(elegidas)


def estratificar(volumen,productos):
    volumen=np.asarray(volumen,dtype=float)
    if len(volumen)!=len(productos) or not np.isfinite(volumen).all() or (volumen<=0).any():
        raise ValueError('Volúmenes semestrales positivos y finitos requeridos.')
    # Terciles por rango, desempate lexicográfico por referencia. No se usan resultados MILP.
    orden=sorted(range(len(productos)),key=lambda i:(volumen[i],productos[i]))
    grupos=np.empty(len(productos),dtype=int)
    for g,indices in enumerate(np.array_split(orden,3)):grupos[indices]=g
    factores=np.empty(len(productos),dtype=float);resumen=[]
    for g in range(3):
        sel=np.flatnonzero(grupos==g);v=volumen[sel]
        factores[sel]=v/v.mean()
        resumen.append(dict(estrato=g+1,n=len(sel),media_unidades=float(v.mean()),
            sd_entre_referencias=float(v.std(ddof=1)),cv_entre_referencias=float(v.std(ddof=1)/v.mean()),
            minimo=float(v.min()),mediana=float(np.median(v)),maximo=float(v.max()),
            media_factor=float(factores[sel].mean()),sd_factor=float(factores[sel].std(ddof=1))))
    return grupos,factores,resumen


def generar(anexo,destino,semilla=SEMILLA):
    from rpm_core import cargar_datos,cargar_datos_extendido,construir_cij_con_imputacion,calibrar_demanda_extendida
    destino=Path(destino)
    if destino.exists() and any(destino.iterdir()):raise ValueError('La salida debe estar vacía; no mezclar versiones.')
    diario=cargar_datos(str(anexo));base=cargar_datos_extendido(str(anexo))
    C=base['cij'];P=C.index.tolist();M=C.columns.tolist()
    if len(P)!=200 or len(set(P))!=200:raise ValueError('Se necesitan las 200 referencias originales únicas.')
    R=construir_cij_con_imputacion(str(anexo),P)['cij'].reindex(index=P,columns=M)
    for A in [C,R]:
        if not np.isfinite(A.to_numpy()).all() or (A.to_numpy()<=0).any():raise ValueError('Matriz de tiempos inválida.')
    S=base['setup'].reindex(M).to_numpy(float)
    if not np.isfinite(S).all() or (S<0).any():raise ValueError('Alistamientos inválidos.')
    cal=calibrar_demanda_extendida(diario['demanda'],base['demanda'])
    nominal=cal['demanda_calibrada'].reindex(P).to_numpy(float)
    # Volumen observado: se toma directamente del anexo, no se reconstruyen fechas.
    ventas=pd.read_excel(anexo,sheet_name='Unidades Vendidas (SEMESTRE)')
    ventas['PRODUCTO']=ventas['PRODUCTO'].astype(str).str.strip()
    if ventas['PRODUCTO'].duplicated().any():raise ValueError('Referencias duplicadas en ventas.')
    V=ventas.set_index('PRODUCTO')['UNIDADES'].reindex(P).to_numpy(float)
    grupos,factores,resumen=estratificar(V,P)
    orden=np.random.default_rng(np.random.SeedSequence([semilla,2])).permutation(len(P))
    filas=[];unicos=set();donantes=[]
    for bloque,(nivel,n,dias) in enumerate(seleccionar_celdas(semilla),1):
        indices=sorted(orden[:n].tolist())
        # Una realización por celda; se mantiene entre las cuatro variantes.
        rng=np.random.default_rng(np.random.SeedSequence([semilla,3,bloque]))
        donor=[int(rng.choice(np.flatnonzero(grupos==grupos[i]))) for i in indices]
        W=factores[donor]
        D=np.floor(nominal[indices]*dias*nivel*W+.5).astype(np.int64)
        for i,k,w,d in zip(indices,donor,W,D):
            donantes.append(dict(bloque_demanda=bloque,producto=P[i],estrato=int(grupos[i]+1),
                donante=P[k],ventas_donante=float(V[k]),factor=float(w),demanda_unidades=int(d),
                nivel_demanda=nivel,referencias_solicitadas=n,horizonte_dias=dias))
        for cap_tipo,matriz_tipo in itertools.product(['nominal','M1_reducida'],['publicada','reconstruida']):
            K=np.full(len(M),1440.);K[M.index('M1')]*=1. if cap_tipo=='nominal' else .75
            A=C if matriz_tipo=='publicada' else R
            datos=dict(productos=[P[i] for i in indices],maquinas=M,demanda=D.tolist(),
                tiempos_min=A.iloc[indices].to_numpy(float).tolist(),setup_min=S.tolist(),
                capacidad_min_dia=K.tolist(),horizonte_dias=dias)
            digest=hashlib.sha256(json.dumps(datos,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
            if digest in unicos:raise ValueError('Problema repetido; no resolver ni sustituir selectivamente.')
            unicos.add(digest);ident=f'E{len(filas)+1:03d}'
            meta=dict(id=ident,nivel_demanda=nivel,referencias_solicitadas=n,
                referencias_activas=int((D>0).sum()),horizonte_dias=dias,capacidad=cap_tipo,
                matriz=matriz_tipo,bloque_demanda=bloque,semilla=semilla,
                naturaleza='sintetico_remuestreo_transversal_estratificado',datos_sha256=digest)
            path=destino/'instancias'/f'{ident}.json';escribir(path,dict(meta=meta,datos=datos))
            filas.append(dict(**meta,archivo=f'instancias/{ident}.json',sha256=sha(path)))
    pd.DataFrame(filas).to_csv(destino/'manifest.csv',index=False,lineterminator='\n')
    pd.DataFrame(resumen).to_csv(destino/'distribucion_estratos.csv',index=False,lineterminator='\n')
    pd.DataFrame(donantes).to_csv(destino/'trazabilidad_demandas.csv',index=False,lineterminator='\n')
    pd.DataFrame(dict(producto=P,ventas_semestre=V,estrato=grupos+1,factor_empirico=factores,
        demanda_diaria_base=nominal)).to_csv(destino/'base_empirica.csv',index=False,lineterminator='\n')
    escribir(destino/'protocolo_generacion.json',dict(n_instancias=100,n_bloques_demanda=25,
        semilla=semilla,naturaleza='remuestreo transversal estratificado',anexo_sha256=sha(anexo),
        generador_sha256=sha(__file__),cargador_sha256=sha(ROOT/'rpm_core.py'),
        factor_calibracion=cal['factor_sesgo'],dias_conversion_nominal=180,
        formula='D_i,s = floor(d_i_base * horizonte * nivel * W_i,s + 0.5)',
        W='Ventas de donante / media de ventas en su estrato; remuestreo con reemplazo.',
        supuesto='Los factores de referencias del mismo estrato son intercambiables para el benchmark sintético.',
        alcance='Heterogeneidad entre productos; NO variabilidad temporal observada de cada producto.',
        datos_temporales_observados=False,celdas_seleccionadas=seleccionar_celdas(semilla),
        diseno='Fraccion estratificada de 25 celdas x 2 capacidades x 2 matrices; sin selección por resultados.',
        hashes_archivos_auxiliares={p.name:sha(p) for p in sorted(destino.glob('*.csv'))},
        ejecuciones_realizadas=0))
    return filas


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--anexo',type=Path,default=ROOT/'AnexodeDatosxlsx.xlsx')
    p.add_argument('--salida',type=Path,required=True);p.add_argument('--semilla',type=int,default=SEMILLA)
    a=p.parse_args();r=generar(a.anexo,a.salida,a.semilla)
    print(f'{len(r)} entradas publicadas; no se ejecutó ningún solver.')
