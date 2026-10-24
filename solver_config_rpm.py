"""PuLP 3.3; CBC, HiGHS y Gurobi WLS. No confundir estado PuLP con certificado."""
import math
import os
import re
import time
from pathlib import Path
import numpy as np
import pulp


def cpu_disponible():
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:
        return os.cpu_count() or 1


def residual(prob):
    errors = []
    for v in prob.variables():
        x = v.value()
        if x is None or not math.isfinite(x):
            return float('inf')
        if v.lowBound is not None: errors.append(max(0, v.lowBound-x))
        if v.upBound is not None: errors.append(max(0, x-v.upBound))
        if v.cat == pulp.LpInteger: errors.append(abs(x-round(x)))
    for c in prob.constraints.values():
        x = c.value()
        if x is None or not math.isfinite(x): return float('inf')
        errors.append(abs(x) if c.sense == 0 else max(0, x) if c.sense == -1 else max(0, -x))
    return max(errors, default=0.)


def resolver(prob, nombre, log, threads=1, seed=42, perfil='base', limite=None):
    """Resolución sin parada por tiempo. Los valores no nulos se rechazan."""
    if limite is not None:
        raise ValueError("No se admite un límite interno de tiempo en producción.")
    log = Path(log); log.parent.mkdir(parents=True, exist_ok=True)
    threads = cpu_disponible() if threads == 0 else max(1, threads)
    warm = any(v.varValue is not None for v in prob.variables())
    opts = {}; env = None
    if nombre == 'CBC':
        opts = dict(presolve=True, cuts=None, strong=5)
        options = [f'randomSeed {seed}', f'randomCbcSeed {seed}', 'heuristicsOnOff on', 'increment 0', 'gomoryCuts on', 'knapsackCuts on', 'probingCuts on']
        if perfil == 'agresivo':
            options += ['probingCuts forceOn', 'gomoryCuts forceOn',
                        'knapsackCuts forceOn', 'flowCoverCuts forceOn',
                        'twoMirCuts forceOn', 'passCuts 50']
        from cbc_actual import CBCActual
        solver = CBCActual(msg=False, logPath=str(log), timeLimit=limite,
                    gapRel=0, gapAbs=0, threads=threads, warmStart=warm,
                    options=options, **opts)
    elif nombre == 'HiGHS':
        class HighsWarm(pulp.HiGHS):
            def callSolver(self, lp):
                import highspy
                known = [v for v in lp.variables() if v.varValue is not None]
                if known:
                    status = lp.solverModel.setSolution(len(known),
                        np.array([v.index for v in known], dtype=np.int32),
                        np.array([v.varValue for v in known], dtype=float))
                    if status != highspy.HighsStatus.kOk:
                        raise RuntimeError('HiGHS rechazó el inicio')
                super().callSolver(lp)
        solver = HighsWarm(msg=True, timeLimit=limite, gapRel=0, gapAbs=0,
                   threads=threads, random_seed=seed, log_file=str(log), log_to_console=False)
    elif nombre == 'Gurobi':
        import gurobipy as gp
        # OutputFlag=0 ANTES de asignar credenciales: evita volcarlas al registro.
        env = gp.Env(empty=True)
        env.setParam('OutputFlag', 0)
        keys = ['WLSACCESSID', 'WLSSECRET', 'LICENSEID']
        from gurobi_rpm import credenciales
        credentials = credenciales()
        vals = [credentials[k] for k in keys]
        if any(vals) and not all(vals):
            env.dispose(); raise ValueError('Faltan credenciales WLS; revisar los tres Secrets')
        if os.environ.get('GITHUB_ACTIONS') and not all(vals):
            env.dispose(); raise ValueError('Configura WLSACCESSID, WLSSECRET y LICENSEID en GitHub Secrets')
        try:
            if all(vals):
                for k, v in zip(keys, vals): env.setParam(k, int(v) if k == 'LICENSEID' else v)
            env.start()
        except Exception:
            env.dispose()
            raise RuntimeError('No se pudo activar Gurobi: revisa licencia WLS, vigencia y conexión') from None
        opts = dict(MIPGap=0, MIPGapAbs=0, Threads=threads, Seed=seed,
                    OutputFlag=1, LogToConsole=0)
        if perfil == 'agresivo':
            opts.update(MIPFocus=3, Cuts=2, Symmetry=2, Presolve=2)
        solver = pulp.GUROBI(env=env, msg=True, warmStart=warm, timeLimit=limite,
                             logPath=str(log), **opts)
    else:
        raise ValueError('Solver desconocido')
    start = time.perf_counter()
    try:
        prob.solve(solver)
        r = dict(solver=nombre, version=None, estado=pulp.LpStatus[prob.status],
                 segundos=time.perf_counter()-start, hilos=threads, semilla=seed,
                 perfil=perfil, limite_interno=limite, gap_rel_objetivo=0,
                 gap_abs_objetivo=0, variables=len(prob.variables()),
                 restricciones=len(prob.constraints), certificado=False, infeasible=False)
        text = log.read_text(errors='replace') if log.exists() else ''
        if nombre == 'CBC':
            r['parametros_cbc']=dict(options=options,presolve=True,cuts=True,strong=opts['strong'],
                                     warmStart=warm,threads=threads,gapRel=0,gapAbs=0,timeLimit=limite)
            ok = bool(re.search(r'^Result - Optimal solution found\s*$', text, re.M))
            r['infeasible'] = bool(re.search(r'Problem is infeasible|Problem proven infeasible', text))
            version = re.search(r'Version:\s*(\S+)',text)
            r['version'] = (version.group(1) if version else 'CBC')+' / cbcbox 2.924'
            from cbc_actual import identidad
            r['implementacion_cbc']=identidad()
            nodes = re.search(r'Enumerated nodes:\s*(\d+)', text)
            r['nodos'] = int(nodes.group(1)) if nodes else None
            if ok:
                r.update(lb=float(pulp.value(prob.objective) or 0), ub=float(pulp.value(prob.objective) or 0), gap_solver=0.)
            else:
                for key, pattern in [('lb', r'Lower bound:\s*([-+\d.eE]+)'), ('ub', r'Objective value:\s*([-+\d.eE]+)')]:
                    m = re.search(pattern,text)
                    if m: r[key] = float(m.group(1))
        elif nombre == 'HiGHS':
            import highspy
            h=prob.solverModel; info=h.getInfo()
            ok=h.getModelStatus()==highspy.HighsModelStatus.kOptimal and info.mip_gap==0
            r.update(infeasible=h.getModelStatus()==highspy.HighsModelStatus.kInfeasible,
                     lb=info.mip_dual_bound, ub=info.objective_function_value,
                     gap_solver=info.mip_gap, nodos=info.mip_node_count, version=h.version())
        else:
            m=prob.solverModel
            ok=m.Status==gp.GRB.OPTIMAL and m.SolCount>0 and m.MIPGap==0
            r.update(infeasible=m.Status==gp.GRB.INFEASIBLE,
                     lb=m.ObjBound, ub=m.ObjVal if m.SolCount else None,
                     gap_solver=m.MIPGap if m.SolCount else None,
                     nodos=m.NodeCount, version='.'.join(map(str,gp.gurobi.version())))
        r['residual_max']=residual(prob)
        r['factible']=r['residual_max']<=1e-5
        r['certificado']=bool(ok and prob.status==pulp.LpStatusOptimal and
                    prob.sol_status==pulp.LpSolutionOptimal and r['factible'])
        return r
    except Exception:
        if nombre == 'Gurobi':
            raise RuntimeError('Gurobi no completó la resolución. Revisa la licencia y el registro del modelo.') from None
        raise
    finally:
        if nombre == 'Gurobi':
            try:
                solver.close()
            finally:
                env.dispose()
