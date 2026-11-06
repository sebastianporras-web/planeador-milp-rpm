# Corrección #19: ejecutor del estudio de sensibilidad

Este paquete reemplaza la entrega «Etapa 1». Incorpora el generador, el MILP común, la heurística, los adaptadores CBC/HiGHS/Gurobi, el auditor de planes, los reportes y el flujo manual de GitHub Actions. No reemplaza la aplicación ni sus resultados históricos.

## Base verificada

El Excel adjunto por el autor coincide byte por byte con AnexodeDatosxlsx.xlsx del repositorio en el commit ff0acda.
SHA-256: 9fda0f31ca72ce70927382fad2a3966de0711f9434f7ac142504e489b074e8f2.

El cargador recupera 200 referencias y 10 máquinas. El caso diario contiene 99 referencias, con 819 tiempos observados y 171 imputados. Las matrices cargadas tienen tiempos positivos; no hay referencias duplicadas ni faltantes en la matriz extendida. Esta revisión verifica consistencia del archivo y su correspondencia con el repositorio, no acredita por sí sola la procedencia de cada medición.

El archivo contiene totales semestrales, no pedidos por fecha. Se trabaja con 144 escenarios deterministas de sensibilidad. Los factores de demanda no son una distribución estimada de ventas. Esta alternativa debe explicarse al director: no equivale a cumplir literalmente su petición de dispersión temporal observada.

## Qué debes hacer ahora

1. Descarga y extrae Correccion_19_Ejecutor.zip. Si aparece una carpeta envolvente, entra hasta ver experimento_19, tests y .github.
2. Abre el repositorio sebastianporras-web/planeador-milp-rpm, pestaña Code, rama main.
3. Usa Add file → Upload files. Arrastra las carpetas experimento_19 y tests. Conserva sus nombres y estructura. Los archivos de tests se agregan a los existentes; no borres la carpeta del repositorio.
4. Publica con el mensaje «Agrega estudio de sensibilidad para #19».
5. Incorpora también .github/workflows/experimento-19.yml. Si no aparece al arrastrar, usa Add file → Create new file; escribe ese nombre completo, copia el contenido del archivo .yml incluido y confirma. No lo guardes en la raíz ni como .yml.txt.
6. No vuelvas a subir el Excel: el existente ya coincide. No reemplaces app.py, requirements.txt, solver_config_rpm.py ni cbc_actual.py. Las dependencias y el presupuesto experimental están aislados dentro de experimento_19.
7. Confirma que GitHub Secrets del repositorio contenga WLSACCESSID, WLSSECRET y LICENSEID. Si ya están configurados y vigentes, no necesitas cambiarlos. No pegues sus valores en comentarios, capturas ni archivos.
8. Abre Actions → Estudio 144 instancias - correccion 19 → Run workflow. Elige main y alcance «piloto»; pulsa Run workflow. GitHub documenta este procedimiento en https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow.
9. Al terminar, abre Artifacts. Descarga estudio19-bloque-0-... e informe-estudio19-.... El piloto contiene UNA instancia con los cuatro métodos; el informe debe indicar 4/576 registros y estado parcial. Eso es esperado.
10. Revisa I001/CBC/resultado.json, I001/HiGHS/resultado.json e I001/Gurobi/resultado.json dentro de resultados_19. Comprueba estado, factible, certificado, objetivo, cotas y auditoría. El flujo verifica primero instalación y licencia, pero no sustituye esta revisión de resultados.
11. Si el piloto funciona, informa al director que solo se dispone del consolidado semestral y que el nuevo diseño usa sensibilidad factorial. Para ejecutar el conjunto elegido, vuelve a Run workflow y selecciona «completo».
12. El modo completo crea 36 bloques de cuatro instancias, en secuencia. Guarda cada bloque como artefacto. Al finalizar, descarga informe-estudio19-... y los 36 bloques. El informe completo debe contener 576 registros: 144 heurísticas y 432 optimizaciones. Los errores, ausencias o interrupciones quedan identificados; no cuentan como certificaciones.

Las ejecuciones remotas no dependen de mantener el navegador abierto. Conserva los artefactos descargados: este flujo solicita 90 días de retención para los bloques, sujeto a las políticas del repositorio.

## Presupuesto y recursos

Se fijan 600 segundos por resolución MILP, un hilo, semilla 42, GAP relativo y absoluto solicitados en cero y ningún warm start. El director permite un presupuesto común en la observación #19. La app mantiene su configuración operativa; este presupuesto se aplica exclusivamente al nuevo experimento.

El límite de tiempo no garantiza GAP cero. Un resultado factible sin prueba, una inviabilidad demostrada y un error son estados diferentes. Cada bloque tiene un límite externo de 180 minutos para proteger la ejecución. Una interrupción externa no se reporta como resultado del solver.

En el peor caso, los 432 MILP consumen hasta 72 horas de presupuesto acumulado, más instalación y exportación. La duración real depende de las instancias. El flujo usa un solo bloque a la vez para evitar concurrencia entre motores y simplificar el uso de la licencia. Verifica los recursos y minutos disponibles en tu cuenta antes de lanzar el conjunto completo.

## Resultados exportados

- resultados_por_instancia.csv: estados, objetivo, tiempos, GAP y factores de cada caso, incluidos ausentes.
- resumen_motores.csv y por_*.csv: tasas de certificación y comportamiento por tamaño, horizonte, demanda, capacidad y matriz.
- comparacion_heuristica.csv: mejora solo cuando ambos planes cubren la demanda completa.
- distribucion_mejoras.csv: cuantiles e intervalos condicionales por remuestreo de bloques; no estiman incertidumbre sobre toda la planta.
- casos_sin_ventaja_o_sin_comparacion.csv: casos que requieren discusión.
- perfil_dolan_more.csv y perfil_desempeno.png: perfil de tiempos de certificación; fallos y ausentes tienen razón infinita.
- estado_informe.json: cobertura y estado del informe.

Los CSV se pueden abrir en Excel; si aparecen en una sola columna, usa Datos → Desde texto/CSV, codificación UTF-8 y delimitador coma. Mantén los JSON y los logs como evidencia técnica.

## Reanudación y versiones

En una carpeta local existente, el ejecutor no repite resultados ya registrados y rechaza protocolos diferentes. En GitHub, una nueva ejecución usa una máquina limpia: no recupera automáticamente artefactos de otra ejecución. No mezcles el piloto con el estudio completo ni ejecuciones de commits, presupuestos o manifiestos distintos. Una repetición por falla de infraestructura debe quedar documentada; no elegir el resultado más favorable.

El reporte rechaza duplicados y modelos diferentes entre motores. No incorpora un plan de la heurística como inicio de los optimizadores. La heurística multidía recorre cada día, ordena demanda pendiente de mayor a menor y asigna primero a máquinas rápidas: es una extensión explícita de la regla diaria, no una nueva práctica corporativa acreditada.

## Qué sigue pendiente

El ejecutor está implementado y probado localmente. No se han ejecutado las 144 instancias con los tres motores. La licencia WLS de tu cuenta y la ejecución real de GitHub se verifican con tu piloto. La alternativa de sensibilidad no reemplaza automáticamente la exigencia de demanda temporal: necesita una justificación metodológica aceptada por el director.

Actualizaremos resultados, resumen, conclusiones, presentación y carta cuando exista el estudio nuevo. No cerrar #19 antes de revisar esas evidencias.
