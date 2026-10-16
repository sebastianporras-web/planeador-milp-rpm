"""Puente explícito PuLP 3.3 -> CBC de cbcbox; usa la acción -solve.

No cambia el modelo ni interpreta una salida por tiempo como óptima.
Los nombres MPS y la lectura de soluciones los gestiona PuLP.
"""
import os
import shlex
import subprocess
import pulp
import cbcbox
import hashlib
import importlib.metadata
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def identidad():
    path=Path(cbcbox.cbc_bin_path())
    return dict(distribucion='cbcbox',version_distribucion=importlib.metadata.version('cbcbox'),
                sha256_ejecutable=hashlib.sha256(path.read_bytes()).hexdigest(),
                rama='CBC Devel; compilación fijada, no CBC 2.10.3 de PuLP')


class CBCActual(pulp.COIN_CMD):
    def __init__(self, **kwargs):
        if kwargs.get('timeLimit') is not None:
            raise ValueError('CBC se ejecuta sin límite interno de tiempo en esta versión.')
        super().__init__(path=cbcbox.cbc_bin_path(), **kwargs)

    def solve_CBC(self, lp, use_mps=True):
        mps,sol,mst=self.create_tmp_files(lp.name,'mps','sol','mst')
        vs,names,rows,_=lp.writeMPS(mps,rename=1)
        args=[self.path,mps]
        if lp.sense==pulp.LpMaximize:args+=['-maximize']
        if self.optionsDict.get('warmStart'):
            self.writesol(mst,lp,vs,names,rows);args+=['-mipStart',mst]
        if self.optionsDict.get('presolve') is not None:
            args+=['-presolve','on' if self.optionsDict['presolve'] else 'off']
        cuts=self.optionsDict.get('cuts')
        if cuts is True:
            args+=['-gomoryCuts','on','-knapsackCuts','on','-probingCuts','on']
        elif cuts is False:args+=['-cuts','off']
        for option in self.options+self.getOptions():
            parts=shlex.split(option);args+=['-'+parts[0]]+parts[1:]
        args+=['-printingOptions','all','-solve' if self.mip else '-initialSolve','-solution',sol,'-quit']
        log=self.optionsDict.get('logPath')
        pipe=open(log,'w',encoding='utf-8') if log else (None if self.msg else open(os.devnull,'w'))
        try:
            result=subprocess.run(args,stdout=pipe,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
            if result.returncode or not os.path.isfile(sol):
                raise pulp.PulpSolverError('CBC no produjo una solución legible; revisar el registro.')
            status,values,dj,pi,slacks,sol_status=self.readsol_MPS(sol,lp,vs,names,rows)
            lp.assignVarsVals(values);lp.assignVarsDj(dj);lp.assignConsPi(pi)
            lp.assignConsSlack(slacks,activity=True);lp.assignStatus(status,sol_status)
            return status
        finally:
            if pipe is not None:pipe.close()
            self.delete_tmp_files(mps,sol,mst)
