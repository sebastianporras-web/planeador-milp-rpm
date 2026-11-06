# Protocolo propuesto para atender la observación #19

## Diseño

Unidad experimental: una instancia definida por demanda, referencias, matriz de tiempos, alistamientos, capacidad por máquina y horizonte. Las repeticiones por semilla del expediente anterior no aumentan el número de instancias.

Diseño completo: 4 niveles de demanda (0.8, 1.0, 1.2, 1.4) × 3 tamaños (99, 150, 200 referencias) × 3 horizontes (1, 3, 5 días) × 2 capacidades × 2 matrices = 144 instancias.

Las capacidades propuestas son 1440 min/día por máquina y un escenario con M1 al 75 % de esa capacidad. El 75 % es un supuesto de estrés explícito, no una frecuencia observada de averías. Mantenerlo fijo antes de conocer los resultados. Las matrices son la publicada en DATOS SIMULADOS, convertida de segundos a minutos por el cargador vigente, y la reconstruida con registros positivos e imputación por media de máquina. «Publicada» no significa íntegramente medida. Los alistamientos conservan los valores del anexo; este factorial no identifica un efecto de su variabilidad.

Una permutación de las 200 referencias, con semilla 19042, fija conjuntos anidados de 99, 150 y 200. Esta selección es una realización por tamaño: no representa todas las posibles mezclas. Los casos históricos pueden conservarse como ilustraciones externas al factorial, con identificación explícita.

La demanda crece con el horizonte: cada caso pide la demanda acumulada de sus días. Este diseño estudia planificación a distintas escalas; no mide el efecto aislado de dar más tiempo a un lote idéntico. Esa pregunta requeriría otro contraste.

## Tratamiento de la variabilidad

Modalidad preferida: bloques de días reales muestreados conjuntamente para todas las referencias. Los niveles multiplicativos son factores de estrés controlados. El mismo vector de demanda se mantiene en las cuatro combinaciones capacidad × matriz de cada celda demanda–tamaño–horizonte. El redondeo usa floor(x + 0.5), admite demanda cero y registra cuántas referencias tienen demanda positiva.

Modalidad provisional: totales semestrales / 180, calibración histórica ya implementada y multiplicación determinista por días y nivel. Esta modalidad no responde por sí sola a la petición de perturbaciones derivadas de dispersión temporal. No convertir la dispersión entre productos en dispersión temporal de cada producto. No conservar la uniforme ±15 % como si fuera un ajuste a ventas.

## Comparación de métodos

La heurística ordena por demanda descendente y asigna primero a las máquinas de menor tiempo unitario, pagando los alistamientos y respetando las capacidades. Para varios días, el ejecutor recorre cada día, reordena por demanda pendiente descendente y asigna a las máquinas de menor tiempo unitario; las pruebas verifican capacidad y cobertura. No denominarla práctica corporativa validada sin respaldo documental de la empresa.

CBC, HiGHS y Gurobi deben recibir el mismo MILP: cantidades enteras, activaciones binarias, demanda total cubierta, capacidades por máquina y día, enlace ajustado y objetivo de tiempo total de producción más alistamientos. Cada motor reconstruye el mismo modelo completo y exporta modelo.lp; el reporte exige que sus huellas coincidan por instancia. Evitar que un motor reciba una descomposición o refuerzo que los otros no reciben en una comparación presentada como comparación de motores.

No cargar comparacion.csv, plan_inicial_3d.csv, resultados históricos ni incumbentes de otro método. Las heurísticas internas de cada motor pueden operar; eso no constituye una solución heredada. Reconstruir el modelo limpio antes de cada motor y comprobar que no hay valores iniciales asignados.

Configuración del ejecutor entregado, que debe mantenerse fija durante el estudio: un hilo por motor, semilla fija, GAP relativo y absoluto solicitados en cero y 600 segundos por optimización. Ese presupuesto experimental permite comparar dificultades y GAP residuales; no garantiza certificación. Mantenerlo separado de la app operativa. La documentación de los motores permite parametrizar tiempo y tolerancias; el límite interno puede superarse ligeramente por tareas finales.

Las 432 optimizaciones consumirían hasta 72 horas acumuladas de presupuesto, sin contar carga, construcción y exportación. Organizar bloques reanudables, con un proceso nuevo por resolución y resultados persistidos después de cada método. Ejecutar los tres motores de una instancia en el mismo equipo, secuencialmente, rotando su orden de forma balanceada. Registrar CPU, RAM, sistema operativo, versiones, parámetros y límites externos. Una interrupción de infraestructura no es un resultado de límite interno del solver.

## Validación y registro

Por instancia y método conservar: hash de entrada y modelo, estado nativo, objetivo incumbente, cota inferior, GAP nativo, GAP calculado, tiempo total, tiempo nativo, nodos, número de variables continuas/enteras/binarias, restricciones, plan y log. Registrar demanda sin cubrir en la heurística.

El auditor recalcula demanda, capacidad, enlace, no negatividad, integridad y objetivo desde el plan exportado. Un estado PuLP «Optimal» aislado no basta para certificar. Exigir terminación óptima nativa, cotas coherentes y factibilidad validada con tolerancias declaradas. Distinguir óptimo numérico, factible sin prueba, inviabilidad demostrada, sin solución encontrada, error e interrupción. No interpretar «sin solución» como «inviable».

## Reportes

- Reducción de carga frente a la heurística solo cuando ambos métodos cubren la misma demanda y cumplen las restricciones. Si la heurística deja demanda pendiente, reportarla como cobertura incompleta; no calcular ahorro comparable sobre una carga menor.
- Distribución por método y estrato: media, mediana, cuantiles, extremos, denominador y número de comparaciones válidas. Separar ahorro frente a incumbentes de ahorro frente a óptimos certificados.
- Fracción certificada sobre todas las instancias programadas, con un cuadro separado para inviabilidades demostradas, errores y ausencias. No retirar casos difíciles para mejorar la tasa.
- Tiempo hasta terminación certificada y GAP al agotar presupuesto. No asignar el tiempo límite como si fuera tiempo de certificación. Los tiempos de no certificación quedan censurados.
- Perfiles Dolan–Moré para los tres motores: razón entre tiempo certificado de cada motor y el menor tiempo certificado de esa instancia. Los fallos tienen razón infinita. Publicar el conjunto y denominador; separar los casos con inviabilidad probada y mostrar también cobertura global.
- Efectos de tamaño, horizonte, nivel de demanda, capacidad y matriz. Registrar casos donde cambia el signo del beneficio o el orden relativo entre motores. No seleccionar únicamente los favorables.
- Si se construyen intervalos por remuestreo, preservar el emparejamiento y los bloques de cuatro variantes capacidad × matriz de una misma demanda. Interpretar el intervalo como condicionado al diseño y al histórico disponible, no como garantía sobre toda la planta. Con una realización por celda no se estima variabilidad dentro de cada celda.

## Cierre documental

Las 60 corridas anteriores pasan a evidencia de repetibilidad de dos casos. Monte Carlo histórico permanece separado, con sus límites y GAP reales. Las nuevas conclusiones dependerán de las 144 instancias ejecutadas; no anticipar superioridad de un motor ni certificación universal. La respuesta a #19 solo puede declararse cerrada cuando existan entradas publicadas, ejecuciones, auditoría de planes y documentos actualizados.

Referencias técnicas para implementación: documentación de solvers de PuLP (https://coin-or.github.io/pulp/technical/solvers.html) y parámetros de Gurobi (https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html). La documentación actual de PuLP no sustituye la comprobación del código instalado 3.3.0.
