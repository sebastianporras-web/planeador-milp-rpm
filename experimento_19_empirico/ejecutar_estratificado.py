"""Una corrida final por método e instancia, con presupuestos fijados por estrato.

La extensión reforzada de Gurobi se registra aparte de los cuatro métodos
comparables. Cada worker se ejecuta en un proceso nuevo y sin warm start.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PUBLICADO = ROOT / 'experimento_19_empirico/entradas_publicadas/manifest.csv'
METODOS = ('Heuristica', 'CBC', 'HiGHS', 'Gurobi', 'Gurobi_reforzado')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def presupuesto(fila):
    n, h = int(fila['referencias_solicitadas']), int(fila['horizonte_dias'])
    if h == 1:
        return 900 if n == 150 else 180
    if h == 3:
        return 1200
    if h == 5:
        return 2700
    raise ValueError(f'Horizonte no previsto: {h}')


def seleccionar(filas, metodo, bloque):
    if metodo == 'Heuristica':
        if bloque != 1:
            raise ValueError('La heurística se ejecuta en un solo trabajo')
        return filas
    if metodo == 'Gurobi_reforzado':
        elegibles = [f for f in filas if int(f['horizonte_dias']) == 5
                     and int(f['referencias_solicitadas']) in (150, 200)]
        if len(elegibles) != 24 or not 1 <= bloque <= 8:
            raise ValueError('El refuerzo debe cubrir los 24 casos grandes de cinco días')
        return elegibles[(bloque - 1) * 3:bloque * 3]
    if len(filas) != 100 or not 1 <= bloque <= 20:
        raise ValueError('La comparación debe cubrir las cien entradas en veinte bloques')
    return filas[(bloque - 1) * 5:bloque * 5]


def principal():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--instancias', type=Path, required=True)
    p.add_argument('--salida', type=Path, required=True)
    p.add_argument('--metodo', choices=METODOS, required=True)
    p.add_argument('--bloque', type=int, default=1)
    a = p.parse_args()
    manifest = a.instancias / 'manifest.csv'
    if sha(manifest) != sha(MANIFEST_PUBLICADO):
        raise ValueError('El manifiesto difiere del conjunto original')
    with manifest.open(encoding='utf-8', newline='') as f:
        filas = list(csv.DictReader(f))
    seleccion = seleccionar(filas, a.metodo, a.bloque)
    a.salida.mkdir(parents=True, exist_ok=True)
    errores = []
    for fila in seleccion:
        entrada = a.instancias / fila['archivo']
        if sha(entrada) != fila['sha256']:
            raise ValueError(f'La entrada {fila["id"]} cambió')
        out = a.salida / fila['id'] / a.metodo
        out.mkdir(parents=True, exist_ok=True)
        limite = presupuesto(fila)
        if a.metodo == 'Gurobi_reforzado':
            cmd = [sys.executable, str(ROOT / 'experimento_19_empirico/extension_certificacion_5d.py'),
                   '--entradas', str(a.instancias), '--salida', str(out),
                   '--id', fila['id'], '--perfil', 'reforzado', '--limite', str(limite)]
        else:
            cmd = [sys.executable, str(ROOT / 'experimento_19_empirico/ejecutar.py'),
                   'worker', '--instancia', str(entrada), '--metodo', a.metodo,
                   '--salida', str(out), '--limite', str(limite),
                   '--threads', '2', '--perfil', 'base']
        with (out / 'ejecucion.log').open('w', encoding='utf-8') as log:
            proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=False)
        resultado = out / 'resultado.json'
        if not resultado.exists():
            errores.append(f'{fila["id"]}: sin resultado, salida {proc.returncode}')
            continue
        r = json.loads(resultado.read_text(encoding='utf-8'))
        if r.get('entrada_sha256') != fila['sha256']:
            errores.append(f'{fila["id"]}: huella de entrada incoherente')
        if proc.returncode or r.get('estado') == 'Error' or r.get('error'):
            errores.append(f'{fila["id"]}: error de ejecución; revisar registro')
        print(f'{fila["id"]} {a.metodo}: {r.get("estado", r.get("estado_nativo"))}; '
              f'certificado={r.get("certificado")}; GAP_pct={r.get("GAP_pct")}', flush=True)
    if errores:
        raise RuntimeError('; '.join(errores))


if __name__ == '__main__':
    principal()
