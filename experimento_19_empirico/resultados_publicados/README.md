# Resultados de las cien instancias

La ejecución [42387073070](https://github.com/sebastianporras-web/planeador-milp-rpm/actions/runs/42387073070) completó diez bloques y su consolidación con éxito. Los cuatro métodos aportan 400 registros, sin ausentes ni errores de ejecución. Esto no significa que todos los problemas tengan solución o un óptimo certificado.

| Método | Plan completo | Óptimo certificado numéricamente | Inviable demostrado | Sin incumbente al límite |
|---|---:|---:|---:|---:|
| Heurística | 68 | No aplica | No aplica | No aplica |
| CBC | 57 | 18 | 24 | 19 |
| HiGHS | 72 | 25 | 24 | 4 |
| Gurobi | 76 | 38 | 24 | 0 |

Los certificados son un subconjunto de los planes completos. El criterio exige plan válido y cierre relativo y absoluto de cotas; una etiqueta nativa `Optimal` no basta. En dos casos Gurobi terminó con ese estado nativo pero no superó el umbral absoluto conservador del estudio.

La auditoría nueva recalculó los planes almacenados, verificó los hashes de las cien entradas y comprobó que los tres motores usaron el mismo LP en cada instancia. Su resumen está en `auditoria_400_resumen.json`; `auditoria_400_registros.csv` conserva también candidatos rechazados y planes parciales. No se ejecutaron nuevas optimizaciones durante esa auditoría.

`resultados_por_instancia.csv` contiene los 400 resultados. `tabla_instancias_100.csv` identifica cada problema, sus factores y su SHA-256. `comparacion_heuristica.csv` solo calcula reducciones de carga cuando ambos métodos completan la misma demanda. Los tamaños de las muestras comparables difieren entre motores; sus medias no deben compararse como si procedieran de las mismas instancias. `mejoras_planes_comparables.csv` resume todas las parejas completas por motor; `distribucion_mejoras.csv` separa certificados e incumbentes.

El perfil de Dolan-Moré usa las 76 instancias sin inviabilidad demostrada y tiempos de certificación. Un caso sin certificado recibe razón infinita. Las 24 inviables permanecen en las tablas globales; su exclusión del perfil no elimina los fracasos de certificación en las otras instancias.

## Construcción e interpretación

El generador registrado antes de resolver seleccionó 25 celdas de demanda, tamaño y horizonte y cruzó cada una con dos capacidades y dos matrices. Los donantes de demanda proceden de tres estratos de volumen semestral; los cuatro casos de una celda comparten la misma realización. Son 100 problemas, no 100 realizaciones independientes de demanda. Los intervalos bootstrap mantienen juntas las variantes de cada celda y describen este diseño condicionado. No estiman variación temporal observada ni demanda futura de RPM.

El protocolo original registra presupuesto común de 180 s por motor, dos hilos, semilla 42 y ausencia de inicio heredado. Los estados, las brechas finales y los tiempos observados permanecen sin sustituir los resultados no certificados. CBC mantuvo `feasibilityPump off`, fijado antes de las cien resoluciones para evitar el fallo nativo documentado en la corrida anterior.

Los registros nativos, planes, modelos, recursos y dependencias se conservan en los diez artefactos `empirico100-bloque-*` de la ejecución. `artefactos_origen.csv` identifica sus hashes y tamaños. El generador y la semilla permiten reproducir las entradas desde el Excel ya publicado. Esta carpeta publica estadísticas de problemas sintéticos e identificadores de ejecución; no replica los nombres de productos ni demandas individuales de cada referencia.

El documento de tesis y su proyecto editable se entregan al autor para revisión. No se modifican ni se publican en este commit.
