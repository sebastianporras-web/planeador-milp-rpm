"""Resuelve sensibilidad nominal con HiGHS, sin límite interno de tiempo."""
from pathlib import Path
import json
import sys
import pandas as pd
import rpm_core as core

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'evidencia_estudio/actualizacion_2026_10_25'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    data=core.cargar_datos(ROOT/'AnexodeDatosxlsx.xlsx')
    C,D,S=data['cij'],data['demanda'],data['setup']
    token=core.RUN_CONTEXT.set({'solver':'HiGHS','log_dir':str(OUT/'logs'),'run_id':'sensibilidad'})
    try:
        # La política histórica aplica cada factor antes del redondeo entero.
        frame=core.comparar_politicas_multiescenario(C,D,S,1440)
        frame.to_csv(OUT/'sensibilidad_demanda_certificada.csv',index=False)
        if not frame.optimo_certificado.all():
            raise RuntimeError('Hay escenarios no certificados; revisar sus registros.')
        D1=core.demanda_entera(D)
        baseline=core._resolver_escenario(C,D1,S,1440)
        caps=pd.Series(1440.,index=C.columns); caps['M8']+=30
        expanded=core._resolver_escenario(C,D1,S,caps)
        if not baseline['gap_certificado'] or not expanded['gap_certificado']:
            raise RuntimeError('El ensayo de capacidad no quedó certificado.')
        result=dict(maquina='M8',incremento_capacidad_min=30,
                    objetivo_base=baseline['valor_objetivo'],
                    objetivo_ampliado=expanded['valor_objetivo'],
                    ahorro_min=baseline['valor_objetivo']-expanded['valor_objetivo'],
                    interpretacion='Ahorro total de minutos al ampliar M8 en 30 min; no es un precio sombra del MILP.')
        (OUT/'capacidad_M8.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(frame.to_string(index=False));print(json.dumps(result,indent=2))
    finally: core.RUN_CONTEXT.reset(token)

if __name__=='__main__': main()
