"""MILP común completo y auditor independiente del plan exportado."""
import math
import numpy as np
import pulp


def arrays(d):
    C=np.asarray(d['tiempos_min'],float); D=np.asarray(d['demanda'],float)
    S=np.asarray(d['setup_min'],float); cap=np.asarray(d['capacidad_min_dia'],float)
    h=d['horizonte_dias']; n=len(d['productos']); m=len(d['maquinas'])
    if isinstance(h,bool) or not isinstance(h,int) or h<1: raise ValueError('Horizonte inválido')
    if C.shape!=(n,m) or D.shape!=(n,) or S.shape!=(m,) or cap.shape!=(m,): raise ValueError('Dimensiones incoherentes')
    if len(set(d['productos']))!=n or len(set(d['maquinas']))!=m: raise ValueError('Etiquetas repetidas')
    if not all(np.isfinite(x).all() for x in [C,D,S,cap]): raise ValueError('Datos no finitos')
    if (C<=0).any() or (D<0).any() or (D!=np.floor(D)).any() or (S<0).any() or (cap<=0).any(): raise ValueError('Valores fuera de dominio')
    return C,D.astype(int),S,cap,h


def construir(d):
    C,D,S,cap,h=arrays(d);n,m=C.shape
    U=np.maximum(0,np.minimum(D[:,None],np.floor((cap[None,:]-S[None,:])/C))).astype(int)
    p=pulp.LpProblem('RPM_EXPERIMENTO',pulp.LpMinimize)
    keys=list(np.ndindex(n,m,h))
    x={k:pulp.LpVariable('x_%d_%d_%d'%k,0,cat='Integer') for k in keys}
    y={k:pulp.LpVariable('y_%d_%d_%d'%k,cat='Binary') for k in keys}
    p+=pulp.lpSum(C[i,j]*x[i,j,t]+S[j]*y[i,j,t] for i,j,t in keys)
    for i in range(n): p+=pulp.lpSum(x[i,j,t] for j in range(m) for t in range(h))==int(D[i]),f'demanda_{i}'
    carga={}
    for j in range(m):
        for t in range(h):
            carga[j,t]=pulp.lpSum(C[i,j]*x[i,j,t]+S[j]*y[i,j,t] for i in range(n))
            p+=carga[j,t]<=float(cap[j]),f'capacidad_{j}_{t}'
    for i,j,t in keys: p+=x[i,j,t]<=int(U[i,j])*y[i,j,t],f'enlace_{i}_{j}_{t}'
    for i in range(n):
        if U[i].max()>0:
            p+=pulp.lpSum(y[i,j,t] for j in range(m) for t in range(h))>=math.ceil(int(D[i])/int(U[i].max())),f'min_setups_{i}'
    # Validez: demanda total por horizonte y días idénticos, sin precedencias.
    for j in range(m):
        for t in range(h-1): p+=carga[j,t]>=carga[j,t+1],f'orden_cargas_{j}_{t}'
    return p,x,y


def auditar(d, X, Y):
    C,D,S,cap,h=arrays(d); n,m=C.shape
    X=np.asarray(X,float); Y=np.asarray(Y,float)
    if X.shape!=(n,m,h) or Y.shape!=X.shape or not np.isfinite(X).all() or not np.isfinite(Y).all():
        return dict(factible=False, motivo='Plan ausente o no finito')
    U=np.maximum(0,np.minimum(D[:,None],np.floor((cap[None,:]-S[None,:])/C)))
    cargas=(C[:,:,None]*X+S[None,:,None]*Y).sum(axis=0)
    residual=dict(demanda=float(np.abs(X.sum(axis=(1,2))-D).max(initial=0)),
        capacidad=float(np.maximum(cargas-cap[:,None],0).max(initial=0)),
        enlace=float(np.maximum(X-U[:,:,None]*Y,0).max(initial=0)),
        integridad=float(max(np.abs(X-np.rint(X)).max(initial=0),np.abs(Y-np.rint(Y)).max(initial=0))),
        dominio=float(max(np.maximum(-X,0).max(initial=0),np.maximum(-Y,0).max(initial=0),np.maximum(Y-1,0).max(initial=0))))
    faltante=np.maximum(D-X.sum(axis=(1,2)),0)
    return dict(factible=max(residual.values())<=1e-5,residuos=residual,
        objetivo_recalculado=float(cargas.sum()),demanda_pendiente=float(faltante.sum()),
        cobertura_unidades=float(X.sum()/D.sum()) if D.sum() else 1., tolerancia=1e-5)


def heuristica(d):
    """Extensión declarada: cada día, demanda pendiente descendente y máquina rápida."""
    C,D,S,cap,h=arrays(d);n,m=C.shape
    X=np.zeros((n,m,h));Y=np.zeros_like(X);pend=D.copy()
    for t in range(h):
        resto=cap.copy()
        for i in sorted(range(n),key=lambda i:(-pend[i],i)):
            for j in sorted(range(m),key=lambda j:(C[i,j],j)):
                q=min(int(pend[i]),max(0,math.floor((resto[j]-S[j])/C[i,j]+1e-10)))
                if q:
                    X[i,j,t]=q;Y[i,j,t]=1;resto[j]-=q*C[i,j]+S[j];pend[i]-=q
                if pend[i]==0:break
    return X,Y
