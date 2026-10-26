# Expediente verificable del estudio RPM

Esta carpeta acompaña la tesis y la aplicación. Conserva evidencia nominal certificada y simulación histórica como experimentos distintos.

## Contenido y reproducción

| Archivo o carpeta | Contenido |
|---|---|
| `evidencia/evidencia_optimizadores.zip` | 60 corridas nominales, planes, cotas, registros y `protocolo.json`; diez repeticiones por solver y horizonte. |
| `evidencia/validacion_historica.zip` | 1000 escenarios históricos, demandas, planes y registros de resolución. |
| `evidencia/AnexodeDatosxlsx.xlsx` | Excel de origen; coincide byte por byte con el de la raíz. |
| `tablas/` | Resúmenes, auditorías y correspondencia de resultados. |
| `fuentes_verificadas/` | Fuentes históricas usadas para comprobar la procedencia; no sustituyen los módulos operativos de la raíz. |
| `historico/monte_carlo_reference_anterior.json` | Referencia anterior recibida en el repositorio, preservada sin cambios. No alimenta los indicadores actuales. |
| `actualizacion_2026_10_25/` | Nuevas resoluciones de sensibilidad y M8, registros y descripción del plan de tres días. |

Desde esta carpeta:

```bash
python -m pip install -r requirements_auditoria.txt
python auditar.py
python auditar_monte_carlo.py
python auditar_procedencia.py
```

Estos scripts extraen las evidencias y recalculan residuos, objetivos y resúmenes. No vuelven a resolver las 60 corridas ni a simular los 1000 escenarios. Conservan los ZIP originales; generan archivos extraídos y tablas de comprobación.

Desde la raíz de la app:

```bash
python actualizar_referencia_monte_carlo.py
python auditar_sensibilidad_actual.py
python -m unittest discover -s tests -v
```

El primer comando recalcula el JSON desde el CSV histórico y registra su SHA-256. El segundo sí ejecuta nuevas optimizaciones con HiGHS sin límite interno. No es necesario repetirlo para consultar los resultados entregados.

## Interpretación

Los 60 planes nominales satisfacen demanda, capacidad, enlaces e integridad dentro de las tolerancias indicadas por los protocolos. Los registros históricos proceden de CBC, HiGHS y Gurobi; su auditoría no constituye una nueva ejecución de esos solvers.

Los 1000 escenarios de Monte Carlo conservan planes factibles. Ninguno registra GAP cero. La media de mejora de sus incumbentes es 15,1876055124 %, con IC normal de la media [15,1396722280; 15,2355387968] %. La evidencia histórica empleó 5 s por escenario y reintentó tres casos a 30 s. La aplicación distingue ese experimento de su protocolo operativo actual sin límite interno.

En sensibilidad, la heurística incumple 69 unidades para el factor 1,1 y 487 para el factor 1,2. No procede calcular una mejora porcentual entre planes que satisfacen demandas distintas; esas celdas permanecen vacías.

## Entornos históricos y actuales

El `protocolo.json` conservado registra literalmente Python 3.14.8. El README de instalación de la copia recibida recomendaba Python 3.12. Son datos de naturaleza distinta: entorno registrado de un experimento e instrucción de instalación. No se modificó retrospectivamente el protocolo. La auditoría de esta entrega utiliza Python 3.12; sus versiones constan en el informe de entrega. La identificación del intérprete histórico descansa en el registro conservado, no en una comprobación independiente de aquel ejecutable.

Las rutas aquí publicadas deben citarse en la siguiente revisión de la tesis. No se ha cambiado automáticamente la numeración o el contenido del PDF actual.
