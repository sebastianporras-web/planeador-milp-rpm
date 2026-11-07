# Estudio sintético de heterogeneidad transversal

## Pregunta y alcance

El estudio compara una heurística reproducible y el mismo MILP resuelto con CBC, HiGHS y Gurobi en 100 instancias distintas. Las ventas semestrales permiten caracterizar diferencias de volumen entre productos. No permiten estimar variación temporal de cada referencia. El conjunto se identifica como benchmark sintético transversal, no como reconstrucción de pedidos diarios ni como pronóstico de la planta.

El director pidió perturbaciones apoyadas en dispersión observada. Este diseño usa la dispersión disponible entre referencias bajo un supuesto explícito de intercambio dentro de estratos de volumen. Es una alternativa metodológica sustentada por los datos existentes; no demuestra dispersión diaria por producto ni garantiza que el director la considere equivalente a esa interpretación de su observación. Las conclusiones quedan condicionadas al generador y al alcance transversal.

## Datos, estratos y generación

La fuente es AnexodeDatosxlsx.xlsx. Se conservan los tiempos nominales y reconstruidos, los alistamientos y la calibración de demanda del código de base. Los 200 volúmenes semestrales se ordenan de menor a mayor; los empates se resuelven por referencia. Tres grupos de 67, 67 y 66 productos definen los estratos. La clasificación no usa resultados de solvers.

Para un producto k del estrato g, el factor empírico es W_k=V_k/media(V_g). La distribución discreta asigna la misma probabilidad a cada donante de ese estrato; su media es uno. Para cada producto i de una instancia se sortea con reemplazo un donante del mismo estrato y se usa:

    D_i,s = floor(d_i_base * h_s * nivel_s * W_donante + 0.5)

La media condicional del factor mantiene la escala nominal antes del redondeo. Su dispersión procede de las ventas entre referencias del estrato. El supuesto de intercambio define una familia de cargas hipotéticas; no identifica una ley temporal de pedidos ni significa que las referencias intercambien tiempos, etiquetas o compatibilidades. Los tiempos de cada producto permanecen con su referencia.

No se recortan factores extremos ni se descartan instancias inviables. Los niveles 0,8; 1,0; 1,2; 1,4 siguen siendo factores de estrés controlados, no probabilidades observadas. La conversión a una base diaria divide por 180 y conserva la calibración previa. Ninguna fecha artificial entra al generador.

## Selección de 100 casos antes de resolver

El espacio de factores contiene 4 niveles de demanda, 3 tamaños (99, 150, 200) y 3 horizontes (1, 3, 5). Una regla latina selecciona 24 celdas; una semilla fija añade una de las 12 omitidas. Los niveles tienen 6 o 7 celdas; los tamaños y horizontes tienen 8 o 9. Cada una de las 25 celdas usa un vector remuestreado independiente y se cruza con:

- Capacidad nominal de 1440 min por máquina y día, o M1 al 75 %.
- Matriz publicada en DATOS SIMULADOS o reconstruida con registros e imputación.

El resultado es 25 x 2 x 2 = 100 problemas. No es un factorial completo. La selección no depende de tiempos, factibilidad ni resultados de ningún método. La semilla es 191007. Los productos forman conjuntos anidados fijados por otra secuencia de esa semilla. Los cuatro casos de una celda mantienen idénticos productos y demanda; solo cambia capacidad o matriz.

Se publican E001 a E100, manifest.csv, base_empirica.csv, distribucion_estratos.csv y trazabilidad_demandas.csv. Cada fila de trazabilidad indica producto, donante, estrato, factor y demanda final. El protocolo conserva huellas del anexo, generador, cargador y archivos auxiliares. No se buscan semillas con resultados favorables.

## Modelo y referencia

La formulación se importa de experimento_19/modelo.py, sin modificarla: cantidades enteras, activaciones binarias, cobertura, capacidades diarias, enlace ajustado, cotas de alistamientos y simetría de días idénticos. Cada motor construye el modelo completo y exporta LP. El informe rechaza huellas distintas entre motores.

La heurística ordena demanda pendiente descendente y prioriza menor tiempo unitario dentro de la capacidad residual, pagando alistamientos. La extensión multidía repite la regla por día. Se trata de la referencia reconstruida del trabajo. La acreditación como práctica corporativa actual necesita respaldo de la empresa; el código no lo prueba.

Cambian las entradas sintéticas y, con ellas, pueden cambiar los valores óptimos. No cambia el objetivo conceptual ni la región factible definida para unas entradas dadas. Los certificados de los casos nominales conservan su identidad.

## Presupuesto común y eficiencia

Cada instancia se ejecuta una vez por método: 100 heurísticas y 300 MILP. Los tres motores usan 180 s, dos hilos y semilla 42; solicitan GAP absoluto y relativo cero. Cada proceso empieza sin valores de variables y sin plan inicial. Los motores rotan su orden por instancia. Las heurísticas internas están permitidas.

El perfil queda fijado como base: CBC con presolve, cortes y heurísticas declarados en el adaptador, con Feasibility Pump desactivada; Gurobi y HiGHS con sus estrategias internas automáticas. Se evita imponer cortes en todos los nodos o forzar búsqueda de cotas antes de conseguir candidatos. El log original de I045/CBC documentó un SIGABRT durante Feasibility Pump, a los 5,22 segundos totales registrados por el ejecutor. Se desactiva esa heurística en todo el conjunto nuevo antes de ejecutarlo; no se reetiqueta el fallo anterior ni se selecciona por instancia una configuración más favorable. Esta elección define el protocolo, no garantiza una mejora universal de velocidad ni elimina todo posible fallo de la biblioteca nativa.

El workflow genera las cien entradas una sola vez y las publica antes de resolver. Diez bloques de diez instancias ejecutan secuencialmente para mantener el aislamiento de recursos y una única sesión WLS simultánea. Cada resultado se persiste al terminar su método. No se recalcula el generador en cada bloque. Los resultados exportados permiten revisar y recuperar diagnósticos sin repetir optimizaciones.

Los 300 MILP acumulan hasta 15 horas de presupuesto interno solicitado. El tiempo real puede ser menor y suma construcción, traducción, licencia y exportación. No se promete duración fija ni certificación universal. Acortar un límite después de observar resultados cambiaría el protocolo; no se hace aquí.

## Estados, evidencia y validación

Se auditan demanda, capacidad, enlace, no negatividad, integridad y objetivo. La certificación exige estado óptimo nativo, cotas cerradas conforme a las tolerancias del trabajo y factibilidad independiente. Un estado PuLP aislado no basta.

El puente CBC conserva comando, MPS, solución si existe, log y código de retorno. Solo una salida normal y un final explícito permiten clasificar límite sin incumbente. Un retorno no cero permanece como error; no se transforma en solución ni inviabilidad. No se reintenta un método para elegir un resultado mejor. Cualquier nueva ejecución debe conservarse como intento distinto y quedar justificada.

El modo verificar prueba el código y publica las 100 entradas sin ejecutar el benchmark; sus pruebas usan casos artificiales separados. El piloto resuelve E001 bajo el protocolo del workflow, pero no se mezcla con el conjunto final. El modo completo solicita 400 registros. La consolidación conserva ausentes y errores y falla su control final si el conjunto completo no está íntegro.

## Análisis y cierre

Se reportan certificaciones con denominador declarado, inviabilidades, errores, tiempo hasta terminación certificada, GAP al agotar presupuesto, perfiles Dolan–Moré y estratos de tamaño, horizonte, demanda, capacidad y matriz. Los no certificados no reciben un tiempo ficticio de certificación. Los casos inviables se separan del perfil y permanecen en los cuadros globales.

La mejora frente a la heurística exige dos planes completos para idéntica demanda. Se informa la demanda sin cubrir cuando corresponda. Las distribuciones distinguen incumbentes de óptimos certificados. Los intervalos por remuestreo de las 25 celdas preservan sus cuatro variantes; son condicionales a la fuente, al generador y a comparaciones válidas, no intervalos de demanda futura.

Se explicarán los casos donde cambia el signo del beneficio o la ventaja de un motor. Los resultados del factorial anterior, pilotos y pruebas locales quedan separados. Monte Carlo histórico no se reetiqueta como comparación certificada de tres motores. La tesis y presentación se actualizarán tras auditar los 400 registros. El número de instancias o un check verde no cierran por sí solos la observación metodológica.

Referencia de la técnica de remuestreo: B. Efron (1979), Bootstrap Methods: Another Look at the Jackknife, The Annals of Statistics 7(1), 1–26, DOI 10.1214/aos/1176344552. Esa referencia fundamenta el remuestreo, no valida por sí sola el supuesto de intercambio de productos adoptado para este benchmark.
