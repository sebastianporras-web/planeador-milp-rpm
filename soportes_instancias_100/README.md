# Soportes del estudio de 100 instancias

Esta carpeta reúne las tablas, los protocolos y las comprobaciones del estudio computacional de RPM Colombia. El conjunto comprende 100 instancias sintéticas y 400 registros: una aplicación de la heurística y una resolución con cada uno de los tres motores (CBC, HiGHS y Gurobi) por instancia.

Los archivos conservan su contenido original. Se copiaron a este expediente sin retirarlos de `experimento_19_empirico`, porque los programas y las pruebas siguen utilizando esas rutas. [INDICE_ARCHIVOS.csv](INDICE_ARCHIVOS.csv) identifica la procedencia y el objeto Git de cada copia.

## Contenido

| Carpeta | Soportes |
|---|---|
| [01_diseno](01_diseno) | Manifiesto de las cien instancias, estratos, factores de diseño, semillas y huellas SHA-256 de las entradas. |
| [02_resultados](02_resultados) | Resultados por instancia y método; estados, resúmenes de motores y desagregaciones por tamaño, horizonte, demanda, capacidad y matriz. |
| [03_comparaciones](03_comparaciones) | Comparación con la heurística, mejoras sobre planes comparables, GAP final, perfil de Dolan–Moré y casos sin ventaja o sin comparación válida. |
| [04_auditoria](04_auditoria) | Revisión de los 400 registros, estados del informe, procedimiento de ejecución y comprobaciones documentales y numéricas. |
| [05_ejecuciones](05_ejecuciones) | Identificadores y huellas de los artefactos originales de GitHub Actions; instrucciones para localizar entradas, planes y registros nativos. |

## Alcance del experimento

El generador seleccionó 25 combinaciones de nivel de demanda, número de referencias y horizonte. Cada combinación se cruzó con dos condiciones de capacidad y dos matrices de tiempos: 25 × 2 × 2 = 100 instancias. Las cuatro variantes de cada combinación comparten una realización de demanda. Los factores se construyeron mediante remuestreo transversal de referencias agrupadas por volumen de ventas; no representan una serie temporal de pedidos observados.

Los tres motores utilizaron el mismo modelo por instancia, sin solución inicial heredada, con dos hilos y un presupuesto común de 180 segundos. Los límites y estados registrados corresponden a las ejecuciones originales; un plan factible sin cierre de cotas no se registra como óptimo certificado.

La auditoría publicada verificó 400 registros y 100 modelos equivalentes entre motores, sin errores en el consolidado. Identificó 24 instancias con inviabilidad concordante. La heurística completó la demanda en 68 instancias; CBC, en 57; HiGHS, en 72; Gurobi, en 76. Entre los planes de los motores, los certificados numéricos fueron 18, 25 y 38, respectivamente. Estos recuentos no deben interpretarse como una tasa de certificación del 100 % ni como resultados de un histórico temporal.

La comparación de reducción de carga utiliza únicamente pares de planes que cubren la misma demanda. El perfil de Dolan–Moré considera los 76 problemas sin inviabilidad demostrada y penaliza las resoluciones que no alcanzaron el certificado. Los archivos conservan también los resultados desfavorables, incompletos y no certificados.

## Procedencia y reproducción

- [Ejecución principal del estudio](https://github.com/sebastianporras-web/planeador-milp-rpm/actions/runs/42387073070): preparación de entradas, diez bloques de resolución e informe consolidado.
- [Artefactos y sus huellas](05_ejecuciones/artefactos_origen.csv): nombres, identificadores, tamaños y SHA-256 de los ZIP originales.
- [Protocolo del experimento](../experimento_19_empirico/PROTOCOLO.md) y [generador de instancias](../experimento_19_empirico/generar_instancias.py).
- [Programa de ejecución](../experimento_19_empirico/ejecutar.py), [consolidación](../experimento_19_empirico/reportar.py) y [auditoría](../experimento_19_empirico/auditar_resultados.py).
- [Resultados originales publicados](../experimento_19_empirico/resultados_publicados/README.md), con criterios de comparación y de certificación.

Los ZIP de GitHub Actions incluyen las entradas desagregadas, modelos, planes y registros nativos. No se duplicaron aquí: el repositorio es público y estas copias contienen solo información que ya figura en sus tablas y metadatos publicados. Los artefactos de Actions tienen vencimiento; véase [05_ejecuciones/LEEME.md](05_ejecuciones/LEEME.md).

Este expediente no modifica la aplicación, las fuentes del estudio, la tesis ni la presentación. Las revisiones posteriores deben distinguirse de la ejecución del 7 de noviembre de 2026, identificada arriba.
