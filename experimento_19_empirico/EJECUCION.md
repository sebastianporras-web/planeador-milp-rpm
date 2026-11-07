# Inicio del estudio completo

La validación remota del commit 053ee2caa71190de30b4e8d060200e314614a835 terminó correctamente en la corrida 42386935692. GitHub comprobó pruebas, generación de 100 entradas y coincidencia con el manifiesto publicado antes de resolver.

Este commit inicia una única ejecución completa: E001 a E100, heurística, CBC, HiGHS y Gurobi, sin inicio heredado, 180 segundos por MILP, dos hilos y perfil base publicado. Las instancias no se regeneran en cada bloque; todos los métodos usan las entradas publicadas por el trabajo preparar.

El estudio evalúa heterogeneidad transversal bajo el supuesto de intercambio dentro de estratos de volumen. No estima variabilidad temporal por referencia. Las 144 instancias anteriores y los pilotos quedan separados.

Al terminar se deben revisar los 400 registros, estados, cotas, GAP y planes. No se declara cerrada la observación ni se anticipan conclusiones antes de esa auditoría.
