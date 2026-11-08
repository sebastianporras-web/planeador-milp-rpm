"""Comparación exploratoria de estrategias de prueba para E029.

No reemplaza el benchmark de 180 s ni modifica sus entradas. Cada caso se
resuelve desde cero. El perfil reforzado agrega desigualdades válidas para
soluciones enteras y aplica parámetros de búsqueda orientados a la cota.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import math
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pulp
from experimento_19.modelo import construir, auditar, arrays, heuristica
from experimento_19_empirico.solver_benchmark import resolver

PILOTOS = ('E029',)


def diagnosticar_holguras(p, tol=1e-5):
    """Describe el incumbente; una restricción floja no es redundante."""
    grupos = {}
    for nombre, restriccion in p.constraints.items():
        valor = restriccion.value()
        if valor is None or not math.isfinite(valor):
            continue
        grupo = next((prefijo for prefijo in (
            'capacidad_', 'enlace_', 'demanda_', 'min_setups_',
            'orden_cargas_', 'cota_carga_referencia_')
            if nombre.startswith(prefijo)), 'otra')
        holgura = abs(valor) if restriccion.sense == 0 else (
            -valor if restriccion.sense == -1 else valor)
        grupos.setdefault(grupo, []).append((nombre, holgura))
    return {grupo: {
        'total': len(filas),
        'activas_en_incumbente': sum(h <= tol for _, h in filas),
        'holgura_min': min(h for _, h in filas),
        'holgura_max': max(h for _, h in filas),
        'menor_holgura': sorted(filas, key=lambda x: x[1])[:8],
    } for grupo, filas in grupos.items()}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reforzar(p, x, y, datos):
    C, D, S, _, h = arrays(datos)
    n, m = C.shape
    cotas = []
    for i in range(n):
        if not D[i]:
            continue
        # Si la referencia se divide, sus preparaciones adicionales no pueden
        # abaratar el costo por debajo de asignar todo a una sola máquina sin
        # restricciones de capacidad. La desigualdad vale para todo plan entero.
        L = float(np.min(D[i] * C[i, :] + S))
        expr = pulp.lpSum(C[i, j] * x[i, j, t] + S[j] * y[i, j, t]
                          for j in range(m) for t in range(h))
        p += expr >= L - 1e-9, f'cota_carga_referencia_{i}'
        cotas.append(L)
    return {'numero_cotas': len(cotas), 'cota_agregada_min': sum(cotas)}


def principal():
    parser = argparse.ArgumentParser()
    parser.add_argument('--entradas', type=Path, required=True)
    parser.add_argument('--salida', type=Path, required=True)
    parser.add_argument('--id', choices=PILOTOS, required=True)
    parser.add_argument('--perfil', choices=('foco2', 'foco3'), required=True)
    parser.add_argument('--limite', type=float, default=1800)
    parser.add_argument('--solo-modelo', action='store_true')
    args = parser.parse_args()
    args.salida.mkdir(parents=True, exist_ok=True)
    entrada = args.entradas / 'instancias' / f'{args.id}.json'
    with (args.entradas / 'manifest.csv').open(encoding='utf-8', newline='') as f:
        meta = next(r for r in csv.DictReader(f) if r['id'] == args.id)
    if sha(entrada) != meta['sha256']:
        raise ValueError('La huella de la instancia no coincide con el manifiesto previo')
    datos = json.loads(entrada.read_text(encoding='utf-8'))['datos']
    if datos['horizonte_dias'] != 5:
        raise ValueError('El piloto solo acepta cinco días')
    p, x, y = construir(datos)
    extra = reforzar(p, x, y, datos)
    lp = args.salida / 'modelo.lp'
    p.writeLP(str(lp))
    informe = {'id': args.id, 'perfil': args.perfil, 'entrada_sha256': sha(entrada),
               'modelo_sha256': sha(lp), 'limite_s': args.limite,
               'threads': 4, 'seed': 42, 'warm_start': False,
               'parametros_gurobi': {'MIPGap': 0, 'MIPGapAbs': 0,
                    'MIPFocus': 2 if args.perfil == 'foco2' else 3,
                    'Cuts': 2, 'Symmetry': 2, 'Presolve': 2}, **extra}
    if args.solo_modelo:
        X, Y = heuristica(datos)
        a = auditar(datos, X, Y)
        if a['factible']:
            C, D, S, _, h = arrays(datos)
            for i in range(len(D)):
                if D[i] and (C[i, :, None] * X[i] + S[:, None] * Y[i]).sum() + 1e-6 < np.min(D[i] * C[i] + S):
                    raise AssertionError(f'Cota no válida para la referencia {i}')
        informe['heuristica_factible'] = a['factible']
        (args.salida / 'resultado.json').write_text(
            json.dumps(informe, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'Modelo preparado: {args.id}, {args.perfil}, {len(p.variables())} variables, {len(p.constraints)} restricciones')
        return
    try:
        inicio = time.perf_counter()
        r = resolver(p, 'Gurobi', args.salida / 'solver.log', threads=4,
                     seed=42, perfil='foco2' if args.perfil == 'foco2' else 'agresivo',
                     limite=args.limite)
        informe['segundos_resolver'] = time.perf_counter() - inicio
        X = np.array([x[i, j, t].value() for i, j, t in np.ndindex(
            len(datos['productos']), len(datos['maquinas']), 5)], dtype=float).reshape(
                len(datos['productos']), len(datos['maquinas']), 5)
        Y = np.array([y[i, j, t].value() for i, j, t in np.ndindex(
            len(datos['productos']), len(datos['maquinas']), 5)], dtype=float).reshape(X.shape)
        a = auditar(datos, X, Y)
        ub, lb = r.get('ub'), r.get('lb')
        objetivo = a.get('objetivo_recalculado') if a.get('factible') else None
        certificado = bool(r.get('certificado') and a['factible'] and ub is not None
                           and abs(ub - objetivo) <= 1e-5)
        informe.update(estado_nativo=r.get('estado_nativo'),
                       estado=r.get('estado'), factible=a['factible'],
                       certificado=certificado, inviabilidad=r.get('infeasible', False),
                       objetivo=objetivo, LB=lb, UB=ub,
                       GAP_pct=100 * abs(objetivo - lb) / max(abs(objetivo), 1e-10)
                       if objetivo is not None and lb is not None and math.isfinite(lb) else None,
                       residuos=a.get('residuos'),
                       version=r.get('version'),
                       nodos=r.get('nodos'),
                       holguras=diagnosticar_holguras(p) if a['factible'] else None)
    except Exception as exc:
        informe.update(error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        (args.salida / 'resultado.json').write_text(
            json.dumps(informe, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
            encoding='utf-8')
    print(json.dumps({k: informe.get(k) for k in
                      ('id', 'perfil', 'factible', 'certificado', 'GAP_pct', 'segundos_resolver')}))


if __name__ == '__main__':
    principal()
