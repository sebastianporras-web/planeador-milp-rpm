"""Recalcula los planes almacenados; no ejecuta optimizadores."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import numpy as np
import pandas as pd


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def auditar(entradas, resultados, salida):
    entradas, resultados, salida = map(Path, [entradas, resultados, salida])
    salida.mkdir(parents=True, exist_ok=True)
    mf = pd.read_csv(entradas / 'manifest.csv').set_index('id')
    assert len(mf) == 100 and mf.index.is_unique
    registros, planes, protocolos = {}, [], []
    for p in resultados.rglob('protocolo_ejecucion.json'):
        protocolos.append(json.loads(p.read_text(encoding='utf-8')))
    assert len(protocolos) == 10 and all(p == protocolos[0] for p in protocolos)
    assert protocolos[0]['manifest_sha256'] == sha(entradas / 'manifest.csv')
    assert protocolos[0]['generacion_sha256'] == sha(entradas / 'protocolo_generacion.json')
    assert protocolos[0]['warm_start'] is False
    for path in resultados.rglob('resultado.json'):
        r = json.loads(path.read_text(encoding='utf-8'))
        key = r['id'], r['metodo']
        assert key not in registros and r['id'] in mf.index, key
        assert not r['estado'].startswith(('Error', 'Interrupcion')), key
        fila = mf.loc[r['id']]
        ipath = entradas / fila.archivo
        assert sha(ipath) == fila.sha256 == r['entrada_sha256'], key
        item = json.loads(ipath.read_text(encoding='utf-8'))
        d = item['datos']
        canonical = json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
        assert hashlib.sha256(canonical).hexdigest() == item['meta']['datos_sha256'], key
        for field in ['limite_s', 'hilos', 'perfil', 'semilla', 'warm_start']:
            assert r[field] == protocolos[0][field], (key, field)
        assert r['codigo_sha256'] == protocolos[0]['codigo_sha256'], key
        if r['metodo'] != 'Heuristica':
            assert sha(path.parent / 'modelo.lp') == r['modelo_sha256'], key
            assert r['solver']['gap_rel_objetivo'] == r['solver']['gap_abs_objetivo'] == 0
            if r['metodo'] == 'CBC':
                assert r['solver']['proceso_cbc']['returncode'] == 0, key
        record = dict(id=key[0], metodo=key[1], estado=r['estado'], plan_exportado=False,
                      factible_recalculado=False, certificado=bool(r['certificado']))
        pp = path.parent / 'plan.csv'
        if pp.exists():
            assert sha(pp) == r['plan_sha256'], key
            v = pd.read_csv(pp)
            n, m, h = len(d['productos']), len(d['maquinas']), d['horizonte_dias']
            X, Y = np.zeros((n, m, h)), np.zeros((n, m, h))
            ii = {p: k for k, p in enumerate(d['productos'])}
            jj = {p: k for k, p in enumerate(d['maquinas'])}
            assert not v.duplicated(['producto', 'maquina', 'dia']).any(), key
            for p, j, t, x, y in v[['producto', 'maquina', 'dia', 'unidades', 'activacion']].itertuples(index=False, name=None):
                assert p in ii and j in jj and 1 <= int(t) <= h, key
                X[ii[p], jj[j], int(t)-1] = x
                Y[ii[p], jj[j], int(t)-1] = y
            assert np.isfinite(X).all() and np.isfinite(Y).all(), key
            C, D, S, K = map(np.asarray, [d['tiempos_min'], d['demanda'], d['setup_min'], d['capacidad_min_dia']])
            U = np.maximum(0, np.minimum(D[:, None], np.floor((K[None, :] - S[None, :]) / C)))
            carga = (C[:, :, None] * X + S[None, :, None] * Y).sum(axis=0)
            residual = dict(demanda=float(np.abs(X.sum(axis=(1, 2))-D).max()),
                            capacidad=float(np.maximum(carga-K[:, None], 0).max()),
                            enlace=float(np.maximum(X-U[:, :, None]*Y, 0).max()),
                            integridad=float(max(np.abs(X-np.rint(X)).max(), np.abs(Y-np.rint(Y)).max())),
                            dominio=float(max(0, -X.min(), -Y.min(), Y.max()-1)))
            factible = max(residual.values()) <= 1e-5
            assert factible == r['factible'], (key, residual)
            obj = float(carga.sum())
            pendiente = float(np.maximum(D-X.sum(axis=(1, 2)), 0).sum())
            assert abs(pendiente-r['demanda_pendiente']) <= 1e-5, key
            if factible:
                assert abs(obj-r['objetivo_factible']) <= 1e-5, key
            record.update(plan_exportado=True, factible_recalculado=factible,
                          objetivo_recalculado=obj, demanda_pendiente=pendiente, **residual)
        else:
            assert r['factible'] is False, key
        if r['certificado']:
            assert r['solver']['certificado'] and record['factible_recalculado'], key
            assert abs(r['UB']-r['LB']) <= 1e-7 and abs(r['UB']-r['LB'])/max(abs(r['UB']), 1e-10) <= 1e-9, key
        registros[key] = r
        planes.append(record)
    expected = {(i, m) for i in mf.index for m in ['Heuristica', 'CBC', 'HiGHS', 'Gurobi']}
    assert set(registros) == expected
    for ident in mf.index:
        rows = [registros[ident, m] for m in ['CBC', 'HiGHS', 'Gurobi']]
        assert len({r['modelo_sha256'] for r in rows}) == 1, ident
        certs = [r['objetivo_factible'] for r in rows if r['certificado']]
        if certs:
            assert max(certs)-min(certs) <= 1e-5, ident
        if any(r.get('inviable_demostrado') for r in rows):
            assert all(r.get('inviable_demostrado') for r in rows), ident
            assert not any(registros[ident, m]['factible'] for m in ['Heuristica', 'CBC', 'HiGHS', 'Gurobi']), ident
    audit = pd.DataFrame(planes)
    audit.to_csv(salida/'auditoria_400_registros.csv', index=False, lineterminator='\n')
    valid = audit[audit.factible_recalculado]
    resumen = dict(registros=400, instancias=100, protocolos_identicos=10, modelos_identicos_entre_motores=100,
                   planes_exportados=int(audit.plan_exportado.sum()), planes_completos_verificados=len(valid),
                   certificados_numericos_verificados=int(audit.certificado.sum()),
                   inviables_concordantes=sum(all(registros[i, m].get('inviable_demostrado', False)
                       for m in ['CBC', 'HiGHS', 'Gurobi']) for i in mf.index), errores=0,
                   residuos_maximos_planes_completos={k: float(valid[k].max()) for k in ['demanda', 'capacidad', 'enlace', 'integridad', 'dominio']},
                   manifest_sha256=sha(entradas/'manifest.csv'),
                   alcance='Auditoría aritmética y documental de planes guardados; no ejecuta solvers ni prueba formalmente la inviabilidad.',
                   auditor_sha256=sha(__file__))
    (salida/'auditoria_400_resumen.json').write_text(json.dumps(resumen, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return audit


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for k in ['entradas', 'resultados', 'salida']:
        p.add_argument('--'+k, required=True)
    auditar(**vars(p.parse_args()))
