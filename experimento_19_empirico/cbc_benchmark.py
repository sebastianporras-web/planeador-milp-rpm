"""Puente CBC con presupuesto y diagnóstico de proceso conservado."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import re
import shlex
import subprocess
import cbcbox
import pulp


def identidad():
    p=Path(cbcbox.cbc_bin_path())
    return dict(distribucion='cbcbox',version_distribucion=importlib.metadata.version('cbcbox'),
                sha256_ejecutable=hashlib.sha256(p.read_bytes()).hexdigest())


class CBCBenchmark(pulp.COIN_CMD):
    def __init__(self,**kwargs):
        super().__init__(path=cbcbox.cbc_bin_path(),**kwargs)
        self.diagnostico={}

    def solve_CBC(self,lp,use_mps=True):
        log=Path(self.optionsDict['logPath']);log.parent.mkdir(parents=True,exist_ok=True)
        mps=log.parent/'modelo.mps';sol=log.parent/'candidato_cbc.sol'
        vs,names,rows,_=lp.writeMPS(str(mps),rename=1)
        args=[self.path,str(mps)]
        if lp.sense==pulp.LpMaximize:args.append('-maximize')
        if self.optionsDict.get('warmStart'):raise ValueError('No se permite warm start en este experimento.')
        if self.optionsDict.get('presolve') is not None:args+=['-presolve','on' if self.optionsDict['presolve'] else 'off']
        if self.timeLimit is not None:args+=['-seconds',str(float(self.timeLimit)),'-timeMode','elapsed']
        for option in self.options+self.getOptions():
            parts=shlex.split(option);args+=['-'+parts[0]]+parts[1:]
        args+=['-printingOptions','all','-solve' if self.mip else '-initialSolve','-solution',str(sol),'-quit']
        (log.parent/'comando_cbc.json').write_text(json.dumps(args,indent=2)+'\n',encoding='utf-8')
        with log.open('w',encoding='utf-8') as f:
            completed=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,check=False)
        self.diagnostico=dict(returncode=completed.returncode,solucion_escrita=sol.is_file(),
            mps_sha256=hashlib.sha256(mps.read_bytes()).hexdigest())
        (log.parent/'proceso_cbc.json').write_text(json.dumps(self.diagnostico,indent=2)+'\n',encoding='utf-8')
        texto=log.read_text(encoding='utf-8',errors='replace')
        # Solo un proceso normal y un desenlace explícito permiten reconocer
        # límite sin candidato. Un retorno no cero sigue siendo un error.
        sin_plan=(completed.returncode==0 and re.search(r'^Result - Stopped on time limit\s*$',texto,re.M)
                  and re.search(r'^No feasible solution found\s*$',texto,re.M))
        if completed.returncode!=0 or (not sol.is_file() and not sin_plan):
            exc=pulp.PulpSolverError('CBC terminó sin una salida interpretable; consultar proceso_cbc.json y solver.log.')
            exc.diagnostico_cbc=self.diagnostico
            raise exc
        if sin_plan:
            for v in vs:v.varValue=None
            lp.assignStatus(pulp.LpStatusNotSolved,pulp.LpSolutionNoSolutionFound)
            return lp.status
        status,values,dj,pi,slacks,solution_status=self.readsol_MPS(str(sol),lp,vs,names,rows)
        lp.assignVarsVals(values);lp.assignVarsDj(dj);lp.assignConsPi(pi)
        lp.assignConsSlack(slacks,activity=True);lp.assignStatus(status,solution_status)
        return status
