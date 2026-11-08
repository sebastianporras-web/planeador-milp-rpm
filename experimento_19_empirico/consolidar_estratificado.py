"""Audita y consolida una sola ejecución estratificada de cien instancias."""
from pathlib import Path
import argparse
import csv
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experimento_19_empirico.ejecutar_estratificado import presupuesto, sha

PRINCIPALES = ('Heuristica', 'CBC', 'HiGHS', 'Gurobi')


def csv_escribir(path, filas, campos):
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction='ignore')
        w.writeheader()
        w.writerows(filas)


def principal():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--instancias', type=Path, required=True)
    p.add_argument('--bloques', type=Path, required=True)
    p.add_argument('--salida', type=Path, required=True)
    a = p.parse_args()
    a.salida.mkdir(parents=True, exist_ok=True)
    with (a.instancias / 'manifest.csv').open(encoding='utf-8', newline='') as f:
        meta = {r['id']: r for r in csv.DictReader(f)}
    if len(meta) != 100:
        raise ValueError('El manifiesto debe contener cien entradas')
    registros = {}
    errores = []
    for path in sorted(a.bloques.glob('**/resultado.json')):
        r = json.loads(path.read_text(encoding='utf-8'))
        ident = r.get('id')
        metodo = r.get('metodo') or 'Gurobi_reforzado'
        if ident not in meta or metodo not in (*PRINCIPALES, 'Gurobi_reforzado'):
            errores.append(f'Registro desconocido: {path}')
            continue
        key = (ident, metodo)
        if key in registros:
            errores.append(f'Duplicado: {key}')
            continue
        registros[key] = r
        if r.get('entrada_sha256') != meta[ident]['sha256']:
            errores.append(f'Entrada distinta: {key}')
        if r.get('estado') == 'Error' or r.get('error'):
            errores.append(f'Error de ejecución: {key}')
        if metodo == 'Gurobi_reforzado' and not (int(meta[ident]['horizonte_dias']) == 5
                and int(meta[ident]['referencias_solicitadas']) in (150, 200)):
            errores.append(f'Refuerzo fuera del estrato: {key}')
    faltantes = [(i, m) for i in meta for m in PRINCIPALES if (i, m) not in registros]
    reforzados = [(i, 'Gurobi_reforzado') for i, f in meta.items()
                  if int(f['horizonte_dias']) == 5
                  and int(f['referencias_solicitadas']) in (150, 200)]
    faltantes += [k for k in reforzados if k not in registros]
    if faltantes:
        errores.append(f'Faltan {len(faltantes)} registros: {faltantes[:8]}')
    for ident, fila in meta.items():
        base = [registros.get((ident, m)) for m in ('CBC', 'HiGHS', 'Gurobi')]
        if not all(base):
            continue
        if len({r.get('modelo_sha256') for r in base}) != 1:
            errores.append(f'Modelo distinto entre motores: {ident}')
        if any(float(r.get('limite_s', -1)) != presupuesto(fila) for r in base):
            errores.append(f'Presupuesto distinto entre motores: {ident}')
    filas = []
    for (ident, metodo), r in sorted(registros.items()):
        m = meta[ident]
        s = r.get('solver') or {}
        filas.append(dict(id=ident, metodo=metodo,
            referencias=int(m['referencias_solicitadas']), dias=int(m['horizonte_dias']),
            nivel=m['nivel_demanda'], capacidad=m['capacidad'], matriz=m['matriz'],
            bloque_demanda=m['bloque_demanda'],
            perfil=r.get('perfil'), limite_s=r.get('limite_s'),
            factible=r.get('factible'), certificado=r.get('certificado'),
            inviable=r.get('inviable_demostrado', r.get('inviabilidad')),
            estado=r.get('estado'), estado_nativo=s.get('estado_nativo', r.get('estado_nativo')),
            LB=r.get('LB'), UB=r.get('UB'), GAP_pct=r.get('GAP_pct'),
            segundos=r.get('segundos_metodo', r.get('segundos_resolver')),
            entrada_sha256=r.get('entrada_sha256'), modelo_sha256=r.get('modelo_sha256')))
    campos = list(filas[0]) if filas else []
    primarias = [r for r in filas if r['metodo'] in PRINCIPALES]
    extras = [r for r in filas if r['metodo'] == 'Gurobi_reforzado']
    csv_escribir(a.salida / 'consolidado_400.csv', primarias, campos)
    csv_escribir(a.salida / 'refuerzo_24.csv', extras, campos)
    resumen = dict(instancias=len(meta), registros_primarios=len(primarias),
                   registros_reforzados=len(extras), completo=not errores,
                   presupuestos_s={'un_dia_99_o_200':180, 'un_dia_150':900,
                                   'tres_dias':1200, 'cinco_dias':2700},
                   errores=errores,
                   certificaciones={metodo:sum(r['certificado'] is True for r in primarias
                                               if r['metodo'] == metodo)
                                    for metodo in PRINCIPALES[1:]},
                   certificaciones_refuerzo=sum(r['certificado'] is True for r in extras))
    (a.salida / 'resumen.json').write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(resumen, ensure_ascii=False), flush=True)
    if errores or len(primarias) != 400 or len(extras) != 24:
        raise SystemExit('Consolidado incompleto o con diferencias')


if __name__ == '__main__':
    principal()
