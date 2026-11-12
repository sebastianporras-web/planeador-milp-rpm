# Estudio de cien instancias — protocolo estratificado

Este expediente corresponde a la comparación central incorporada en la tesis `Trabajo_RPM.pdf`, edición del 11 de noviembre de 2026. Los resultados se conservan separados del estudio anterior publicado en `experimento_19_empirico/resultados_publicados/`.

## Procedencia

- Ejecución GitHub Actions: [42441274388](https://github.com/sebastianporras-web/planeador-milp-rpm/actions/runs/42441274388).
- Inicio registrado (UTC): **2026-11-08 03:06:06**; última actualización (UTC): **2026-11-09 13:43:17**.
- Rama fuente: `estudio-100-estratificado`; commit fuente: `731298d86316f706c0f975c74e8432032e1de3fb`.
- Estado del flujo completo: **failure**. El documento indica que el fallo ocurrió durante la exportación posterior de cuatro diagnósticos auxiliares de inviabilidad. La existencia de los 400 registros se comprueba mediante el CSV conservado, pero no debe confundirse con la finalización exitosa del flujo completo.
- Archivos de este expediente: extraídos del editable `TeXstudio.rar` suministrado para la tesis; procedencia de los archivos comprobable con el manifiesto SHA-256 incluido. La publicación no implica una nueva ejecución de los optimizadores.

## Protocolo de la comparación

Diseño de 25 celdas de demanda estratificada cruzadas con dos capacidades y dos matrices: 100 problemas. La semilla de generación es **191007**. Cada problema utiliza el mismo MILP para CBC, HiGHS y Gurobi, sin solución inicial heredada en este experimento; dos hilos, semilla 42 y alternancia del orden. El presupuesto asignado depende del tamaño y horizonte y es idéntico para los tres motores dentro de cada instancia. Los segundos precisos se encuentran en `datos_resultados_estratificados/consolidado_400.csv`, columna `limite_s`. No es el mismo protocolo que el de 180 segundos fijos por motor del estudio anterior.

La certificación numérica requiere un estado compatible, plan válido y cierre absoluto y relativo de cotas. Los resultados se interpretan bajo tolerancias numéricas y no como una prueba formal del código del optimizador.

## Resultados del consolidado

| Motor | Planes completos | Óptimos certificados | Inviabilidades reportadas | Sin incumbente al límite | GAP máximo entre completos (%) |
|---|---:|---:|---:|---:|---:|
| CBC | 54 | 20 | 24 | 22 | 13.362308 |
| HiGHS | 76 | 31 | 24 | 0 | 3.606103 |
| Gurobi | 76 | 41 | 24 | 0 | 0.179452 |

La heurística completa la demanda en **68** casos. Hay 400 registros en total, incluidos los 100 de la heurística. El consolidado guarda 100 identificadores únicos y los hash de las instancias coinciden con `datos_estudio_100/tabla_instancias_100.csv` en las tres soluciones MILP (300 cotejos).

La mejora media de Gurobi frente a la heurística es **21,8123 %**, calculada exclusivamente sobre **68** parejas con demanda completa en ambos planes. Los GAP positivos no se presentan como certificados de optimalidad. El estudio de los 60 certificados nominales de uno y tres días tiene otro protocolo y continúa en `evidencia_estudio/nominal_2026_10_25/`.

## Archivos y trazabilidad

- `datos_estudio_100/protocolo_generacion.json`: método de construcción, semilla y huellas de archivos de origen.
- `datos_estudio_100/tabla_instancias_100.csv`: identidad y SHA-256 de las cien instancias.
- `datos_resultados_estratificados/consolidado_400.csv`: 400 filas con estado, LB, UB, GAP, tiempos, presupuesto y huella del modelo/entrada.
- `datos_resultados_estratificados/heuristica_base.csv`: referencia heurística y demanda pendiente.
- `datos_resultados_estratificados/comparacion_heuristica_100.csv`: parejas de planes completos.
- `datos_resultados_estratificados/resumen_comparacion_heuristica.csv`: medias e intervalos condicionales.
- `datos_resultados_estratificados/perfil_factores_100.csv`: perfil de tiempos de certificación.
- `MANIFEST_SHA256.csv`: huella y tamaño en bytes de cada soporte publicado aquí.

Los CSV de resultados no contienen los registros nativos completos de cada motor; para inspeccionar tales archivos debe consultarse la ejecución original y sus artefactos, según disponibilidad. El expediente histórico de 180 segundos permanece sin modificaciones; las cifras de sus certificaciones no se mezclan con las de esta ejecución.
