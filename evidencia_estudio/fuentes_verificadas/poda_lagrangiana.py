"""Reducción por cotas lagrangianas y programación dinámica entera.

Para lambda>=0: L=sum_i f_i(lambda)-h*cap*sum_j lambda_j <= Z*.
Si f_ij(q,n)-f_i+L>UB, el par (q,n) no mejora el inicio factible.
No se usa una cota óptima conocida de otra ejecución ni de otro solver.
"""
from collections import deque
import json
import time
from pathlib import Path
import numpy as np
import pulp
from cbc_actual import CBCActual


def etapa(prev,rate,setup,u,h):
    out=prev.copy();grid=np.arange(len(prev));base=prev-rate*grid
    for k in range(1,h+1):
        lo=(k-1)*u+1;hi=k*u
        if u<=0 or lo>=len(prev):break
        dq=deque()
        for t in range(lo,len(prev)):
            x=t-lo
            while dq and base[dq[-1]]>=base[x]:dq.pop()
            dq.append(x)
            while dq and dq[0]<t-hi:dq.popleft()
            value=base[dq[0]]+rate*t+setup*k
            if value<out[t]:out[t]=value
    return out


def envolvente(points):
    points=sorted(set(points))
    if len(points)<=1:return points
    def cruz(o,a,b):return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    low=[];up=[]
    for point in points:
        while len(low)>1 and cruz(low[-2],low[-1],point)<=0:low.pop()
        low.append(point)
    for point in reversed(points):
        while len(up)>1 and cruz(up[-2],up[-1],point)<=0:up.pop()
        up.append(point)
    return low[:-1]+up[:-1]


def calcular(C,D,S,cap,h,plan,ub,folder):
    from optimizar_rpm import construir
    folder=Path(folder);start=time.perf_counter()
    c=C.to_numpy();d=D.to_numpy(dtype=int);s=S.to_numpy()
    # Mantiene el modelo completo si el tamaño de la DP no resulta práctico.
    if d.sum()>200000 or d.max(initial=0)>50000:
        return None,dict(aplicada=False,motivo='Dominio grande para programación dinámica',segundos=time.perf_counter()-start)
    p,*_=construir(C,D,S,cap,h,set())
    lp=CBCActual(mip=False,msg=False,logPath=str(folder/'relajacion_lp.log'))
    p.solve(lp)
    lam=np.zeros(len(S))
    if p.status==pulp.LpStatusOptimal:
        for j in range(len(S)):
            pi=p.constraints[f'cap_agregada_{j}'].pi
            if pi is not None and np.isfinite(pi):lam[j]=max(0.,-float(pi))
    # Cualquier lambda no negativo da una cota válida: la optimalidad LP
    # no es una premisa del descarte. Si falla, lambda=0 conserva validez.
    U=np.maximum(0,np.minimum(d[:,None],np.floor((cap-s)/c))).astype(int)
    def dp(i,exclude=None):
        prev=np.full(int(d[i])+1,np.inf);prev[0]=0
        for j in range(len(S)):
            if j!=exclude:
                prev=etapa(prev,c[i,j]*(1+lam[j]),s[j]*(1+lam[j]),int(U[i,j]),h)
        return prev
    costs=np.array([dp(i)[-1] for i in range(len(D))])
    lb=float(costs.sum()-h*cap*lam.sum())
    if not np.isfinite(lb):raise ValueError('No hay cota lagrangiana finita')
    tau=max(1e-5,1e-8*max(1.,abs(ub),abs(lb),float(np.abs(costs).sum())))
    if lb>ub+tau:raise ValueError('La cota no es compatible con el inicio factible')
    bounds={};records=[]
    for i in range(len(D)):
        for j in range(len(S)):
            other=dp(i,exclude=j);points=[]
            for n in range(h+1):
                q=np.arange(n,min(int(d[i]),n*int(U[i,j]))+1,dtype=int) if n else np.array([0])
                values=other[d[i]-q]+(c[i,j]*q+s[j]*n)*(1+lam[j])
                keep=q[values<=costs[i]+ub-lb+tau]
                if len(keep):
                    points.extend([(int(keep[0]),n),(int(keep[-1]),n)])
                    records.append(dict(i=i,j=j,n=n,q_min=int(keep[0]),q_max=int(keep[-1])))
            if not points:raise ValueError('Reducción vacía: revisar precisión y datos')
            bounds[i,j]=points
    # Verifica que el inicio usado para UB sigue dentro de cada envolvente.
    a=plan.groupby(['producto','maquina']).unidades.sum()
    n=plan.groupby(['producto','maquina']).dia.nunique()
    for (i,j),points in bounds.items():
        q0=int(a.get((C.index[i],C.columns[j]),0));n0=int(n.get((C.index[i],C.columns[j]),0))
        at_n=[q for q,nn in points if nn==n0]
        if not at_n or not min(at_n)<=q0<=max(at_n):
            raise ValueError('La poda excluyó el inicio: no se continúa')
    report=dict(aplicada=True,metodo='Cota lagrangiana + DP entera por referencia',
        cota_lagrangiana=lb,UB_inicio=float(ub),margen_numerico=tau,lambda_maquinas=lam.tolist(),
        pares=len(bounds),pares_fijados_cero=sum(max(q for q,n in pts)==0 for pts in bounds.values()),
        segundos=time.perf_counter()-start,
        certificado_externo_utilizado=False,dominios=records)
    (folder/'poda.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return bounds,report


def aplicar(p,A,N,X,Y,domains,dias,detalladas):
    for (i,j),points in domains.items():
        a=A[i,j];n=N[i,j]
        a.lowBound=min(q for q,k in points);a.upBound=max(q for q,k in points)
        n.lowBound=min(k for q,k in points);n.upBound=max(k for q,k in points)
        hull=envolvente(points)
        if len(hull)==2:
            (x0,y0),(x1,y1)=hull
            p+=(x1-x0)*(n-y0)-(y1-y0)*(a-x0)==0,f'poda_recta_{i}_{j}'
        elif len(hull)>2:
            for k,((x0,y0),(x1,y1)) in enumerate(zip(hull,hull[1:]+hull[:1])):
                p+=(x1-x0)*(n-y0)-(y1-y0)*(a-x0)>=0,f'poda_hull_{i}_{j}_{k}'
        if j in detalladas:
            for t in range(dias):
                X[i,j,t].upBound=min(X[i,j,t].upBound,a.upBound)
                if a.upBound==0:Y[i,j,t].upBound=0
