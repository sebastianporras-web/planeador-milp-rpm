"""Comprobación de instalación y licencia; no cuenta como instancia del estudio."""
import os

def verificar():
    import gurobipy as gp
    import highspy
    import cbcbox
    keys=('WLSACCESSID','WLSSECRET','LICENSEID')
    if not all(os.environ.get(k,'').strip() for k in keys):
        raise RuntimeError('Faltan WLSACCESSID, WLSSECRET o LICENSEID en GitHub Secrets.')
    env=gp.Env(empty=True)
    try:
        env.setParam('OutputFlag',0)
        for k in keys:env.setParam(k,int(os.environ[k]) if k=='LICENSEID' else os.environ[k])
        env.start()
        m=gp.Model(env=env)
        try:
            x=m.addVar(vtype=gp.GRB.INTEGER,lb=0);m.addConstr(x>=2.4);m.setObjective(x)
            m.Params.MIPGap=0;m.Params.MIPGapAbs=0;m.Params.Threads=1;m.Params.TimeLimit=30;m.optimize()
            if m.Status!=gp.GRB.OPTIMAL or abs(m.ObjVal-3)>1e-7:raise RuntimeError('Falla la prueba mínima de Gurobi.')
        finally:m.dispose()
    except Exception:
        raise RuntimeError('Gurobi no superó la comprobación. Revisar licencia WLS, vigencia y conectividad.') from None
    finally:env.dispose()
    print('Entorno y prueba mínima de licencia disponibles; no se imprimen credenciales.')

if __name__=='__main__':verificar()
