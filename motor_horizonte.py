"""Demanda fija, máquinas variables, capacidad diaria repetida y preparaciones por día.

Maestro agregado como relajación + desagregación exacta de máquinas cuyo reparto
no se verifica. Una heurística sólo acredita factibilidad, nunca optimalidad.
"""
import math
import time
from fractions import Fraction as F
from pathlib import Path
import numpy as np
import pandas as pd
import pulp
from scipy.optimize import linprog
from scipy.sparse import coo_matrix
from solver_config_rpm import resolver as resolver_backend
from optimizar_rpm import guardar

TOL=1e-5

def resolver(prob,nombre,log,**kwargs):
    audit=resolver_backend(prob,nombre,log,**kwargs)
    # CBC también demuestra inviabilidad durante presolve sin emitir el resumen final.
    # En estos modelos todas las variables están acotadas: no existe objetivo no acotado.
    if nombre=='CBC' and prob.status==pulp.LpStatusInfeasible and not audit['infeasible']:
        text=Path(log).read_text(errors='replace') if Path(log).exists() else ''
        bounded=all(v.lowBound is not None and v.upBound is not None and
                    math.isfinite(v.lowBound) and math.isfinite(v.upBound) for v in prob.variables())
        if bounded and ('Presolve determined that the problem was infeasible' in text or
                        'Pre-processing says infeasible or unbounded' in text):
            audit.update(infeasible=True,factible=False,certificado=False,
                         prueba_inviabilidad='CBC presolve; estado Infeasible; todas las variables con cotas finitas.')
    return audit

class Datos:
    def __init__(self,d):
        self.raw=d;self.ids=d['ids'];self.maquinas=d['maquinas']
        raw_d=np.array(d['D'],dtype=float)
        if not np.isfinite(raw_d).all() or np.any(raw_d!=np.round(raw_d)):raise ValueError('La demanda debe ser entera y finita.')
        self.c=np.array(d['C'],dtype=float);self.d=raw_d.astype(np.int64)
        self.s=np.array(d['S'],dtype=float);self.cap=np.array(d['cap'],dtype=float)
        self.I=range(len(self.ids));self.J=range(len(self.maquinas))
        if self.c.shape!=(len(self.ids),len(self.maquinas)):raise ValueError('Dimensiones inconsistentes.')
        if len(set(self.ids))!=len(self.ids) or len(set(self.maquinas))!=len(self.maquinas):raise ValueError('IDs duplicados.')
        if not all(np.isfinite(v).all() for v in [self.c,self.d,self.s,self.cap]):raise ValueError('Datos no finitos.')
        if (self.c<0).any() or (self.d<1).any() or (self.s<0).any() or (self.cap<=0).any():raise ValueError('Datos fuera de rango.')
        self.U={};self.cost={}
        for i in self.I:
            for j in self.J:
                if self.c[i,j]<=0:continue
                # División racional de los decimales almacenados; no redondear capacidades hacia arriba.
                c=F(str(self.c[i,j]));s=F(str(self.s[j]));cap=F(str(self.cap[j]))
                u=max(0,min(int(self.d[i]),int((cap-s)//c)))
                if u:
                    self.U[i,j]=u;self.cost[i,j]=c+s/u
        self.pairs=list(self.U);self.by_i={i:[j for j in self.J if (i,j) in self.U] for i in self.I}
        self.by_j={j:[i for i in self.I if (i,j) in self.U] for j in self.J}
        missing=[self.ids[i] for i in self.I if not self.by_i[i]]
        if missing:raise ValueError('Sin máquina capaz de producir una unidad con preparación: '+', '.join(missing[:12]))

def cota(datos):
    """Cota válida por precios de capacidad. El LP sólo propone los precios.

    Reconstruir y normalizar precios no negativos con Fraction garantiza que
    sum(cap_j*mu_j)=1 y pi_i=min_j((c_ij+s_j/U_ij)*mu_j).
    H >= sum(D_i*pi_i). No se usa el objetivo aproximado del LP como prueba.
    """
    n=len(datos.pairs);ni=len(datos.ids);nj=len(datos.maquinas)
    eq=coo_matrix((np.ones(n),([i for i,j in datos.pairs],range(n))),shape=(ni,n+1)).tocsr()
    rr=[j for i,j in datos.pairs]+list(datos.J)
    cc=list(range(n))+[n]*nj
    vv=[float(datos.cost[i,j]) for i,j in datos.pairs]+[-v for v in datos.cap]
    ub=coo_matrix((vv,(rr,cc)),shape=(nj,n+1)).tocsr()
    lp=linprog(np.r_[np.zeros(n),1.],A_ub=ub,b_ub=np.zeros(nj),A_eq=eq,b_eq=datos.d,bounds=(0,None),method='highs')
    mu=np.ones(nj)
    if lp.success and np.isfinite(lp.ineqlin.marginals).all():mu=np.maximum(0,-lp.ineqlin.marginals)
    if not mu.any():mu=np.ones(nj)
    prices=[F(str(float(v))) for v in mu]
    scale=sum(F(str(float(cap)))*v for cap,v in zip(datos.cap,prices))
    prices=[v/scale for v in prices]
    pi=[min(datos.cost[i,j]*prices[j] for j in datos.by_i[i]) for i in datos.I]
    bound=sum(int(datos.d[i])*pi[i] for i in datos.I)
    ceil=lambda v:(v.numerator+v.denominator-1)//v.denominator
    throughput=max(math.ceil(int(datos.d[i])/sum(datos.U[i,j] for j in datos.by_i[i])) for i in datos.I)
    lower=max(1,ceil(bound),throughput)
    allocation=[]
    if lp.success:
        for i in datos.I:
            entries=[(j,max(0.,float(lp.x[k]))) for k,(ii,j) in enumerate(datos.pairs) if ii==i]
            amounts={j:int(math.floor(v)) for j,v in entries};remaining=int(datos.d[i])-sum(amounts.values())
            if remaining<0 or remaining>len(entries):allocation=[];break
            for j,v in sorted(entries,key=lambda item:-(item[1]-math.floor(item[1])))[:remaining]:amounts[j]+=1
            allocation.extend([i,j,q] for j,q in amounts.items() if q)
    return dict(asignacion_inicio=allocation,dias_inferiores=lower,cota_continua=float(bound),cota_unidades=throughput,
                numerador=str(bound.numerator),denominador=str(bound.denominator),
                precios=[str(v) for v in prices],lp_usado=bool(lp.success),
                criterio='Cota de capacidad con precios duales reconstruidos racionalmente; considera c+S/U y pares habilitados.')

def validar(datos,P,h,objetivo=None):
    # Índices internos enteros; exportación con IDs se hace después de validar.
    demand=np.zeros(len(datos.ids),dtype=np.int64);loads={};seen=set();obj=[]
    integ=link=neg=0.
    for r in P.itertuples():
        i=int(r.i);j=int(r.j);t=int(r.t);q=float(r.q)
        if r.i!=i or r.j!=j or r.t!=t or (i,j) not in datos.U or not 0<=t<h:
            raise ValueError('Plan fuera del dominio.')
        if (i,j,t) in seen or not math.isfinite(q):raise ValueError('Asignación duplicada o no finita.')
        seen.add((i,j,t));integ=max(integ,abs(q-round(q)));neg=max(neg,-q)
        if q<=0:raise ValueError('El plan disperso debe contener sólo cantidades positivas.')
        link=max(link,q-datos.U[i,j]);demand[i]+=round(q)
        value=q*datos.c[i,j]+datos.s[j];obj.append(value);loads[j,t]=loads.get((j,t),0.)+value
    err=float(np.max(np.abs(demand-datos.d)))
    excess=max([0.]+[v-datos.cap[j] for (j,t),v in loads.items()])
    objective=math.fsum(obj);delta=0. if objetivo is None else abs(objective-objetivo)
    ok=max(err,excess,integ,link,neg,delta)<=TOL
    return dict(factible=bool(ok),error_demanda=err,exceso_capacidad=excess,
                error_integridad=integ,error_enlace=max(0.,link),error_no_negatividad=max(0.,neg),
                objetivo=objective,diferencia_objetivo=delta,preparaciones=len(P),
                utilizacion_media_pct=100*objective/(h*float(datos.cap.sum())))

def heuristica(datos,asignacion=None,h=None,orden=0):
    """Construye un plan factible, sin acreditar mínimo ni óptimo de costo."""
    bins={j:[] for j in datos.J};rows={}
    items=list(datos.I)
    if orden==0:items.sort(key=lambda i:-int(datos.d[i])*min(datos.c[i,j] for j in datos.by_i[i]))
    elif orden==1:items.sort(key=lambda i:-min(datos.c[i,j] for j in datos.by_i[i]))
    for i in items:
        jobs=[(j,int(asignacion.get((i,j),0))) for j in datos.by_i[i]] if asignacion is not None else [(None,int(datos.d[i]))]
        for fixed,amount in jobs:
            left=amount
            while left:
                candidates=[]
                for j in ([fixed] if fixed is not None else datos.by_i[i]):
                    for t,load in enumerate(bins[j]):
                        setup=0. if (i,j,t) in rows else datos.s[j]
                        room=math.floor((datos.cap[j]-load-setup)/datos.c[i,j])
                        room=min(room,datos.U[i,j]-rows.get((i,j,t),0))
                        if room>0:
                            candidates.append((t,datos.c[i,j]+setup/min(left,room),j,min(left,room)));break
                    t=len(bins[j])
                    if h is None or t<h:candidates.append((t,datos.c[i,j]+datos.s[j]/min(left,datos.U[i,j]),j,min(left,datos.U[i,j])))
                if not candidates:return None
                t,_,j,q=min(candidates)
                if t==len(bins[j]):bins[j].append(0.)
                setup=0. if (i,j,t) in rows else datos.s[j]
                bins[j][t]+=q*datos.c[i,j]+setup;rows[i,j,t]=rows.get((i,j,t),0)+q;left-=q
    P=pd.DataFrame([(i,j,t,q) for (i,j,t),q in rows.items()],columns=['i','j','t','q'])
    H=int(P.t.max())+1
    return P if validar(datos,P,h or H)['factible'] else None

def construir(datos,h,detalladas,optimizacion,limite_variables,plan=None):
    size=2*len(datos.pairs)+2*h*sum(len(datos.by_j[j]) for j in detalladas)
    if size>limite_variables:raise MemoryError(f'El siguiente maestro requiere aproximadamente {size:,} variables; supera la protección de memoria configurada ({limite_variables:,}). No se demuestra inviabilidad.')
    p=pulp.LpProblem('RPM_demanda_fija',pulp.LpMinimize);A={};N={};X={};Y={}
    for i,j in datos.pairs:
        u=datos.U[i,j];d=int(datos.d[i]);A[i,j]=pulp.LpVariable(f'A_{i}_{j}',0,min(d,h*u),cat='Integer')
        N[i,j]=pulp.LpVariable(f'N_{i}_{j}',0,min(h,d),cat='Integer')
        p+=A[i,j]<=u*N[i,j];p+=N[i,j]<=A[i,j]
        k,r=divmod(d,u)
        if r and k and d<h*u:p+=A[i,j]<=r*N[i,j]+k*(u-r)
    cost=pulp.lpSum(datos.c[i,j]*A[i,j]+datos.s[j]*N[i,j] for i,j in datos.pairs)
    p+=cost if optimizacion else pulp.lpSum(A.values()) # constante positiva: cualquier factible es óptimo de factibilidad
    for i in datos.I:p+=pulp.lpSum(A[i,j] for j in datos.by_i[i])==int(datos.d[i])
    for j in datos.J:
        p+=pulp.lpSum(datos.c[i,j]*A[i,j]+datos.s[j]*N[i,j] for i in datos.by_j[j])<=h*datos.cap[j]
        if j not in detalladas:continue
        for i in datos.by_j[j]:
            for t in range(h):
                X[i,j,t]=pulp.LpVariable(f'x_{i}_{j}_{t}',0,datos.U[i,j],cat='Integer')
                Y[i,j,t]=pulp.LpVariable(f'y_{i}_{j}_{t}',cat='Binary')
                p+=X[i,j,t]<=datos.U[i,j]*Y[i,j,t];p+=X[i,j,t]>=Y[i,j,t]
            p+=pulp.lpSum(X[i,j,t] for t in range(h))==A[i,j]
            p+=pulp.lpSum(Y[i,j,t] for t in range(h))==N[i,j]
        loads=[pulp.lpSum(datos.c[i,j]*X[i,j,t]+datos.s[j]*Y[i,j,t] for i in datos.by_j[j]) for t in range(h)]
        for v in loads:p+=v<=datos.cap[j]
        for t in range(h-1):p+=loads[t]>=loads[t+1]
    if plan is not None:
        counts=plan.groupby(['i','j']).q.sum().to_dict();setups=plan.groupby(['i','j']).size().to_dict()
        full={(int(r.i),int(r.j),int(r.t)):int(r.q) for r in plan.itertuples()}
        for i,j in datos.pairs:A[i,j].setInitialValue(counts.get((i,j),0));N[i,j].setInitialValue(setups.get((i,j),0))
        for j in detalladas:
            order=sorted(range(h),key=lambda t:-sum(datos.c[i,j]*full.get((i,j,t),0)+datos.s[j]*(full.get((i,j,t),0)>0) for i in datos.by_j[j]))
            for i in datos.by_j[j]:
                for t,old in enumerate(order):q=full.get((i,j,old),0);X[i,j,t].setInitialValue(q);Y[i,j,t].setInitialValue(int(q>0))
    return p,A,N,X,Y

def distribuir(datos,h,j,a,n,folder,solver,seed,limite_variables):
    active=[i for i in datos.by_j[j] if a[i]>0]
    if not active:return pd.DataFrame(columns=['i','j','t','q']),None
    if 2*len(active)*h>limite_variables:raise MemoryError('El reparto diario supera la protección de memoria. Sin conclusión de factibilidad.')
    p=pulp.LpProblem('Reparto',pulp.LpMinimize);x={};y={}
    for i in active:
        for t in range(h):
            x[i,t]=pulp.LpVariable(f'x_{i}_{t}',0,datos.U[i,j],cat='Integer');y[i,t]=pulp.LpVariable(f'y_{i}_{t}',cat='Binary')
            p+=x[i,t]<=datos.U[i,j]*y[i,t];p+=x[i,t]>=y[i,t]
        p+=pulp.lpSum(x[i,t] for t in range(h))==a[i];p+=pulp.lpSum(y[i,t] for t in range(h))==n[i]
    loads=[pulp.lpSum(datos.c[i,j]*x[i,t]+datos.s[j]*y[i,t] for i in active) for t in range(h)]
    for v in loads:p+=v<=datos.cap[j]
    for t in range(h-1):p+=loads[t]>=loads[t+1]
    p+=pulp.lpSum(x.values())
    audit=resolver(p,solver,folder.with_suffix('.log'),threads=1,seed=seed);guardar(folder.with_suffix('.json'),audit)
    if not audit['factible']:return None,audit
    rows=[(i,j,t,round(x[i,t].value())) for i in active for t in range(h) if x[i,t].value()>0.5]
    return pd.DataFrame(rows,columns=['i','j','t','q']),audit

def resolver_h(datos,h,folder,solver='HiGHS',seed=42,optimizacion=False,plan=None,limite_variables=250000):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);start=time.perf_counter();audits=[];detailed=set()
    result=dict(horizonte=h,solver=solver,semilla=seed,estado='Sin conclusión',certificado=False,factible=False,iteraciones=audits)
    def finish():
        if optimizacion and not result['certificado'] and not result['factible'] and plan is not None and result['estado']=='Sin conclusión':
            accept(plan,{},False)
            result['estado']='Factible; optimalidad sin certificar'
        result['segundos']=time.perf_counter()-start;guardar(folder/'resultado.json',result);return result
    def accept(P,audit,optimal=False):
        v=validar(datos,P,h,audit.get('lb') if optimal else None)
        if not v['factible']:raise ValueError('El plan no supera la validación independiente.')
        P.to_csv(folder/'plan_interno.csv',index=False)
        out=P.rename(columns={'i':'Referencia','j':'Maquina','t':'Dia','q':'Unidades'}).copy()
        out.Referencia=out.Referencia.map(dict(enumerate(datos.ids)));out.Maquina=out.Maquina.map(dict(enumerate(datos.maquinas)));out.Dia+=1
        out['Producto']=out.Referencia.map({r['ID']:r['Producto'] for r in datos.raw['nombres']})
        out.to_csv(folder/'plan.csv',index=False)
        result.update(estado='Óptimo certificado' if optimal else 'Factible verificado',factible=True,certificado=optimal,
                      validacion=v,objetivo=v['objetivo'],LB=audit.get('lb') if optimal else None,GAP_pct=0. if optimal else None)
    try:
        if plan is not None and not validar(datos,plan,h)['factible']:raise ValueError('Inicio no factible.')
        if not optimizacion and plan is not None:accept(plan,{});return finish()
        for k in range(len(datos.maquinas)+1):
            guardar(folder/'avance.json',dict(fase='Construcción del maestro',iteracion=k,horizonte=h,maquinas_detalladas=[datos.maquinas[j] for j in detailed]))
            p,A,N,X,Y=construir(datos,h,detailed,optimizacion,limite_variables,plan)
            guardar(folder/'avance.json',dict(fase='Resolviendo maestro',iteracion=k,horizonte=h,variables=len(p.variables()),restricciones=len(p.constraints)))
            audit=resolver(p,solver,folder/f'maestro_{k:02d}.log',threads=1,seed=seed);guardar(folder/f'maestro_{k:02d}.json',audit);audits.append(audit)
            if audit['infeasible']:result['estado']='Inviable demostrado';return finish()
            if not audit['certificado']:return finish()
            if optimizacion and plan is not None and abs(validar(datos,plan,h)['objetivo']-audit['lb'])<=TOL:
                accept(plan,audit,True);return finish()
            allocation={(i,j):round(A[i,j].value()) for i,j in datos.pairs}
            if not optimizacion:
                for order in [0,1,2]:
                    candidate=heuristica(datos,allocation,h,order)
                    if candidate is not None:accept(candidate,{});return finish()
            parts=[];bad=[]
            for j in datos.J:
                if j in detailed:
                    part=pd.DataFrame([(i,j,t,round(X[i,j,t].value())) for i in datos.by_j[j] for t in range(h) if X[i,j,t].value()>0.5],columns=['i','j','t','q'])
                else:
                    guardar(folder/'avance.json',dict(fase='Verificando reparto diario',iteracion=k,horizonte=h,maquina=datos.maquinas[j]))
                    a={i:allocation[i,j] for i in datos.by_j[j]};n={i:round(N[i,j].value()) for i in datos.by_j[j]}
                    part,check=distribuir(datos,h,j,a,n,folder/f'reparto_{k:02d}_{j:03d}',solver,seed,limite_variables)
                    if part is None:bad.append(j);break
                parts.append(part)
            if bad:detailed.update(bad);continue
            candidate=pd.concat(parts,ignore_index=True)
            accept(candidate,audit,optimizacion);return finish()
    except Exception as exc:
        result['estado']='Sin conclusión';result['error']=str(exc)
    return finish()

def buscar(datos,folder,solver='HiGHS',limite_variables=250000,solo_cotas=False):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);started=time.perf_counter()
    state=dict(estado='Calculando cotas',minimo_certificado=False,pruebas=[])
    def save():
        state['segundos_busqueda']=time.perf_counter()-started
        guardar(folder/'busqueda.json',state)
    save();bound=cota(datos);state['cota']=bound;lower=bound['dias_inferiores'];save()
    P=heuristica(datos)
    allocation={(i,j):q for i,j,q in bound.get('asignacion_inicio',[])}
    if allocation:
        for order in [0,1,2]:
            alternative=heuristica(datos,allocation,orden=order)
            if alternative is not None and (P is None or alternative.t.max()<P.t.max()):P=alternative
    if P is None:raise RuntimeError('No se pudo construir la cota superior factible.')
    upper=int(P.t.max())+1
    if lower>upper:raise ValueError('Inconsistencia entre cota inferior y plan factible; revisar precisión.')
    state.update(inferior=lower,superior=upper,horizonte_factible=upper,validacion_plan=validar(datos,P,upper),estado='Buscando horizonte mínimo')
    P.to_csv(folder/'inicio_comun.csv',index=False);save()
    # El intervalo es [lower, upper]. Un UNKNOWN nunca aumenta lower.
    while lower<upper and not solo_cotas:
        h=(lower+upper)//2
        state['probando']=h;save()
        # Primero intentar plan sin solver, sólo como prueba de factibilidad.
        candidate=heuristica(datos,h=h)
        check=resolver_h(datos,h,folder/f'H_{h}',solver,optimizacion=False,plan=candidate,limite_variables=limite_variables)
        state['pruebas'].append(check)
        if check['factible']:
            upper=h;P=pd.read_csv(folder/f'H_{h}'/'plan_interno.csv')
        elif check['estado']=='Inviable demostrado':lower=h+1
        else:state['estado']='Intervalo sin cerrar';break
        state.update(inferior=lower,superior=upper,horizonte_factible=upper,validacion_plan=validar(datos,P,upper))
        P.to_csv(folder/'inicio_comun.csv',index=False);save()
    state.update(inferior=lower,superior=upper,minimo_certificado=lower==upper,
                 estado='Horizonte mínimo certificado' if lower==upper else 'Intervalo sin cerrar')
    if lower==upper:state['horizonte_minimo']=upper
    state['horizonte_factible']=upper;state['validacion_plan']=validar(datos,P,upper)
    P.to_csv(folder/'inicio_comun.csv',index=False)
    guardar(folder/'prueba_un_dia.json',dict(horizonte=1,estado='Inviable demostrado por cota' if lower>1 else ('Factible verificado' if upper==1 else 'Sin conclusión'),
              criterio='H >= cota inferior demostrada',cota_inferior=lower))
    save();return state
