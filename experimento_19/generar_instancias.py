"""Diseño factorial reproducible. No resuelve modelos ni inventa resultados.
Ejecutar desde la raíz del repositorio: python experimento_19/generar_instancias.py ...
"""
from pathlib import Path
import argparse
import hashlib
import itertools
import json
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def escribir(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Bytes estables en Windows y Linux; no depender de la traducción de newlines.
    path.write_bytes((json.dumps(data, ensure_ascii=False, sort_keys=True,
                                indent=2, allow_nan=False) + '\n').encode('utf-8'))


def leer_historico(path, productos):
    d = pd.read_csv(path, encoding='utf-8-sig', dtype={'Referencia': str})
    if list(d.columns) != ['Fecha', 'Referencia', 'Unidades']:
        raise ValueError('Encabezados requeridos: Fecha,Referencia,Unidades.')
    d['Referencia'] = d.Referencia.str.strip()
    d['Fecha'] = pd.to_datetime(d.Fecha, format='%Y-%m-%d', errors='raise')
    if d.Fecha.isna().any() or (d.Fecha != d.Fecha.dt.normalize()).any():
        raise ValueError('Fecha debe identificar días completos, sin horas ni vacíos.')
    d['Unidades'] = pd.to_numeric(d.Unidades, errors='raise')
    v = d.Unidades.to_numpy(float)
    if not np.isfinite(v).all() or (v < 0).any() or (v != np.floor(v)).any():
        raise ValueError('Unidades deben ser enteros no negativos.')
    if d.duplicated(['Fecha', 'Referencia']).any():
        raise ValueError('Una fila por fecha y referencia; agrega primero los pedidos del día.')
    if set(d.Referencia) != set(productos):
        raise ValueError('El histórico debe contener exactamente las referencias del anexo.')
    p = d.pivot(index='Fecha', columns='Referencia', values='Unidades').sort_index()
    if p.isna().any().any():
        raise ValueError('Faltan observaciones fecha–referencia. No se imputan ceros automáticamente.')
    if len(p) < 30:
        raise ValueError('Se requieren al menos 30 días registrados para este protocolo; no garantiza representatividad.')
    if not ((p.index[1:] - p.index[:-1]).days == 1).all():
        raise ValueError('Faltan fechas del calendario. Registra explícitamente días sin demanda como cero.')
    return p.reindex(columns=productos)


def generar(anexo, destino, historico=None, semilla=19042,
            factorial_exploratorio=False, capacidad=1440., reduccion=.75):
    from rpm_core import cargar_datos, cargar_datos_extendido, construir_cij_con_imputacion, calibrar_demanda_extendida
    destino = Path(destino)
    if destino.exists() and any(destino.iterdir()):
        raise ValueError('Usa una carpeta vacía para no mezclar versiones del experimento.')
    if (historico is None) == (not factorial_exploratorio):
        raise ValueError('Elige histórico real o --factorial-exploratorio, nunca ambos.')
    if not np.isfinite(capacidad) or capacidad <= 0 or not 0 < reduccion < 1:
        raise ValueError('Capacidad positiva y factor de reducción entre 0 y 1 requeridos.')
    base = cargar_datos_extendido(str(anexo))
    diario = cargar_datos(str(anexo))
    C = base['cij']; productos = C.index.tolist(); maquinas = C.columns.tolist()
    if len(productos) != 200 or len(set(productos)) != 200:
        raise ValueError('Este diseño requiere las 200 referencias originales únicas.')
    R = construir_cij_con_imputacion(str(anexo), productos)['cij'].reindex(index=productos, columns=maquinas)
    for matriz in (C, R):
        if not np.isfinite(matriz.to_numpy()).all() or (matriz <= 0).any().any():
            raise ValueError('Matriz incompleta o tiempos no positivos.')
    S = base['setup'].reindex(maquinas).to_numpy(float)
    if not np.isfinite(S).all() or (S < 0).any():
        raise ValueError('Alistamientos inválidos.')
    cal = calibrar_demanda_extendida(diario['demanda'], base['demanda'])
    nominal = cal['demanda_calibrada'].reindex(productos).to_numpy(float)
    H = leer_historico(historico, productos) if historico else None
    # Selección común y anidada: los tamaños cambian referencias, no los coeficientes.
    orden = np.random.default_rng(semilla).permutation(len(productos))
    filas = []; hashes = set()
    for numero, (nivel, n, dias, cap_tipo, matriz_tipo) in enumerate(itertools.product(
            [.8, 1., 1.2, 1.4], [99, 150, 200], [1, 3, 5],
            ['nominal', 'M1_reducida'], ['publicada', 'reconstruida']), 1):
        idx = sorted(orden[:n].tolist())
        # Se reutiliza la demanda en las cuatro combinaciones capacidad × matriz.
        clave = int(round(nivel * 10)) * 10000 + n * 10 + dias
        rng = np.random.default_rng(np.random.SeedSequence([semilla, clave]))
        inicio = None
        if H is not None:
            # Bloque conjunto de días consecutivos: conserva asociaciones entre productos
            # y dependencia dentro del horizonte; no mezcla días independientes por SKU.
            inicio = int(rng.integers(0, len(H) - dias + 1))
            demanda = H.iloc[inicio:inicio + dias].sum(axis=0).to_numpy(float) * nivel
        else:
            demanda = nominal * dias * nivel
        D = np.floor(demanda[idx] + .5).astype(np.int64)
        caps = np.full(len(maquinas), capacidad)
        if cap_tipo != 'nominal':
            caps[maquinas.index('M1')] *= reduccion
        matriz = C if matriz_tipo == 'publicada' else R
        datos = dict(productos=[productos[i] for i in idx], maquinas=maquinas,
                     demanda=D.tolist(), tiempos_min=matriz.iloc[idx].to_numpy(float).tolist(),
                     setup_min=S.tolist(), capacidad_min_dia=caps.tolist(), horizonte_dias=dias)
        content_hash = hashlib.sha256(json.dumps(datos, sort_keys=True,
            ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
        if content_hash in hashes:
            raise ValueError('Dos celdas generan el mismo problema; revisar diseño antes de ejecutar.')
        hashes.add(content_hash)
        ident = f'I{numero:03d}'
        meta = dict(id=ident, nivel_demanda=nivel, referencias_solicitadas=n,
                    referencias_activas=int((D > 0).sum()), capacidad=cap_tipo,
                    factor_capacidad_M1=float(reduccion if cap_tipo != 'nominal' else 1),
                    matriz=matriz_tipo, semilla=semilla, subsemilla=clave,
                    inicio_bloque=str(H.index[inicio].date()) if H is not None else None,
                    naturaleza='bootstrap_empirico_bloques' if H is not None else 'sensibilidad_determinista_exploratoria',
                    datos_sha256=content_hash)
        path = destino / 'instancias' / f'{ident}.json'
        escribir(path, dict(meta=meta, datos=datos))
        filas.append(dict(**meta, horizonte_dias=dias, archivo=f'instancias/{ident}.json', sha256=sha(path)))
    pd.DataFrame(filas).to_csv(destino/'manifest.csv', index=False, encoding='utf-8', lineterminator='\n')
    escribir(destino/'protocolo_generacion.json', dict(
        n_instancias=len(filas), anexo_sha256=sha(anexo), generador_sha256=sha(__file__),
        historico_sha256=sha(historico) if historico else None,
        codigo_carga_sha256=sha(ROOT/'rpm_core.py'), semilla=semilla,
        factor_calibracion_solo_exploratorio=cal['factor_sesgo'] if H is None else None,
        capacidad_nominal_min_dia=capacidad, factor_reduccion_M1=reduccion,
        regla_redondeo='floor(demanda + 0.5)', horizonte='demanda acumulada durante h días',
        demanda_temporal_observada=H is not None,
        observacion='El modo exploratorio no estima una distribución temporal de ventas y no cierra la observación #19.',
        ejecuciones_realizadas=0, pandas=pd.__version__, numpy=np.__version__))
    return filas


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--anexo', type=Path, default=ROOT/'AnexodeDatosxlsx.xlsx')
    p.add_argument('--salida', type=Path, required=True)
    p.add_argument('--historico', type=Path)
    p.add_argument('--factorial-exploratorio', action='store_true')
    p.add_argument('--semilla', type=int, default=19042)
    a = p.parse_args()
    filas = generar(a.anexo, a.salida, a.historico, a.semilla, a.factorial_exploratorio)
    print(f'{len(filas)} instancias generadas; ningún optimizador ejecutado.')
