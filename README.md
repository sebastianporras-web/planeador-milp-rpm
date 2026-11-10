# Planeación RPM Colombia

## Inicio
`python -m pip install -r requirements.txt`
`streamlit run app.py`

El perfil de despliegue conserva Gurobi para no retirar una función existente.
Para instalar sin Gurobi: `python -m pip install -r requirements-base.txt`.
`requirements-gurobi.txt` añade Gurobi al perfil base. La licencia se configura
por separado; no se distribuye con el repositorio. `requirements_rpm_v3.txt`
es el perfil heredado de ejecución por consola, sin paquetes duplicados.

## Estructura
- `app.py`: aplicación operativa, carga y modo Demanda total.
- `pages/2_Analisis_del_estudio.py`: entrada a `analisis_tesis.py`.
- `rpm_core.py`: formulación y análisis diarios/históricos.
- `solver_config_rpm.py`: ejecución y auditoría de CBC, HiGHS y Gurobi.
- `certificacion_numerica.py`: cierre numérico y error tipado de certificación.
- `optimizar_rpm.py` e `integracion_selectiva.py`: solución multiperiodo selectiva.
- `monte_carlo_reference.json`: referencia histórica ORIGINAL en la raíz.
  Está incluido en la raíz. La copia histórica anterior se conserva por separado.

## Solvers y resultados
HiGHS es el valor predeterminado; CBC está disponible y Gurobi depende de su
instalación y licencia. PuLP modela el problema; no es un solver.
Las evidencias nominales históricas reportan 11.547,4126 min (1 día) y
34.132,1434 min (3 días), para sus instancias concretas. No se usan estos
valores como respuestas fijas de una nueva carga. Diez repeticiones por solver
y horizonte: 60 corridas. Los tres días utilizan arranque informado.

## Credenciales
Configurar WLSACCESSID, WLSSECRET y LICENSEID en Streamlit Secrets o entorno.
No escribir sus valores en README, código, capturas ni archivos ZIP.

## Variables de entorno
- RPM_SOLVER: CBC, HiGHS o Gurobi; valor predeterminado HiGHS.
- RPM_SEED: semilla, 42 por defecto en la ruta de rpm_core.
- RPM_RUN_ID: identificador de ejecución; los escenarios añaden un sufijo único.
- RPM_LOG_DIR: directorio de registros, logs_cbc por defecto.
- RPM_COTA_AGREGADA: activa (1) la cota agregada en la ruta multiperiodo completa.

## Línea de comandos
`python optimizar_rpm.py --help`
Ejemplo con directorio de entrada ya preparado:
`python optimizar_rpm.py --datos datos_rpm --salida resultados_rpm_v3 --solver HiGHS --dias 3 --threads 1 --seed 42`
El argumento --datos es un directorio en el formato que espera el programa;
no debe confundirse con el Excel cargado desde la interfaz.

## Certificación
No se establece límite interno de tiempo. GAP relativo y absoluto objetivo: 0.
HiGHS/Gurobi requieren estado óptimo, solución factible verificada y cierre
numérico: GAP relativo <= 1e-9 Y |UB-LB| <= 1e-7 min; valores finitos.
La tolerancia de factibilidad existente es 1e-5, separada de las anteriores.
Las cotas y el GAP devueltos se conservan. El certificado es numérico, no
aritmética racional exacta. CBC conserva su comprobación del mensaje final
óptimo y de factibilidad, con procedencia explícita de sus cotas reconstruidas.

## Análisis por escenarios
Un retorno sin certificado se registra individualmente y no cancela el lote.
No se convierte un objetivo de relajación o un faltante en cero. Los resúmenes
certificados excluyen los casos no certificados e informan su cantidad.
Los errores de datos y programación siguen visibles; no se capturan como si
fueran una simple falta de óptimo. Cada retorno guarda un JSON en RPM_LOG_DIR.
Un escenario que no retorna puede seguir ocupando el proceso: el registro
no equivale a un límite de tiempo ni evita una terminación por falta de RAM.

## Recursos y conservación
Los registros crecen en disco. Archivar y revisar su retención fuera del lote;
esta revisión no elimina evidencia automáticamente. .gitignore evita nuevas
subidas accidentales, pero NO deja de rastrear archivos ya comprometidos.
No ejecutar lotes grandes en Streamlit durante la sustentación hasta comprobar
memoria y registros del despliegue real. El hosting mantiene límites externos.

## Pruebas
`python tests/test_revision.py`
Las pruebas usan instancias pequeñas y escenarios de fallo controlados.
No sustituyen las 60 certificaciones ni una prueba de carga del servidor.

## Instancia de regresión y privacidad
`python validar_instancia.py` comprueba la instancia nominal publicada, no una carga arbitraria.
El repositorio se encuentra público. `AnexodeDatosxlsx.xlsx` y su copia del expediente están accesibles. Antes de difundir el enlace, comprobar que RPM autorizó publicar esos datos. Si requieren reserva, revisar permisos y copias del historial; borrar solo el archivo actual no elimina las versiones anteriores.

## Expediente del estudio
La carpeta `evidencia_estudio/` conserva las evidencias nominales y la validación histórica, los scripts y sus hashes. Su README explica la reproducción. Los planes históricos se auditan sin ejecutar nuevamente los optimizadores.

## Versión del entorno
Instalación comprobada en Python 3.12. Las versiones históricas de las corridas constan en el protocolo conservado dentro de evidencia_estudio; no se reemplazan por la versión del entorno de esta revisión.

## Estudio de cien instancias

La ejecución completa y su auditoría están en [experimento_19_empirico/resultados_publicados](experimento_19_empirico/resultados_publicados/). La consulta por tipo de soporte se hace desde [soportes_instancias_100](soportes_instancias_100/), donde figuran el manifiesto, las tablas y el inventario de procedencia. Ambos directorios contienen algunos CSV y JSON idénticos: el primero mantiene las rutas usadas por los scripts; el segundo agrupa la documentación para revisión.

El estudio reúne 400 registros de cuatro métodos, estados, brechas y perfiles de cien problemas sintéticos. Los resultados distinguen optimalidad numérica, planes completos sin certificado e inviabilidad; no afirman que las cien instancias tengan GAP cero.

El estudio factorial previo de 144 instancias permanece en [experimento_19](experimento_19/) como antecedente, sin mezclarse con los resultados del estudio vigente de cien instancias.

Los resúmenes nominales del 25 de octubre y la distinción entre sus versiones de Python y las del respaldo anterior están en [evidencia_estudio/nominal_2026_10_25](evidencia_estudio/nominal_2026_10_25/). El PDF del repositorio y el RAR de fuentes siguen siendo la versión anterior: el autor revisará el nuevo editable antes de publicarlo.

## Copias de conservación y control de versiones

- `AnexodeDatosxlsx.xlsx` aparece en la raíz para los programas y en `evidencia_estudio/evidencia/` para el expediente. Ambas rutas contienen el mismo archivo.
- `evidencia_estudio/fuentes_verificadas/` conserva fuentes utilizadas en la comprobación de procedencia. Algunas coinciden exactamente con los módulos actuales; otras representan versiones diferentes. No conviene sustituirlas sin repetir la auditoría.
- El protocolo de generación figura tanto en entradas como en resultados del estudio nuevo. El segundo ejemplar documenta el protocolo asociado a los resultados publicados.
- `soportes_instancias_100/` reúne 24 copias exactas de archivos que permanecen en `experimento_19_empirico/`. El inventario permite comprobar su identidad por objeto Git. No deben confundirse con experimentos adicionales.
- Los resultados del 17 y del 25 de octubre corresponden a ejecuciones distintas. Se conservan en sus carpetas originales, sin combinar estadísticas ni reemplazar trazas.

Los archivos con contenido idéntico comparten un objeto en Git. Su presencia en varias rutas facilita las comprobaciones y no duplica por sí sola ese objeto en el historial. Los archivos CSV y JSON de los expedientes mantienen sus bytes originales durante el checkout para evitar alteraciones de las huellas por diferencias de fin de línea.
