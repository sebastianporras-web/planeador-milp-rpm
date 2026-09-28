# Planeación MILP | Extrusión-soplado

## Archivos

- `app.py`: interfaz Streamlit.
- `rpm_core.py`: carga de datos, imputación, modelo MILP y análisis.
- `AnexodeDatosxlsx.xlsx`: instancia de la tesis; contiene datos de planta.
- `monte_carlo_reference.json`: referencia histórica agregada.
- `requirements.txt`: dependencias de Python.
- `validar_instancia.py`: comprobación del caso base.

## Ejecución local

Usar Python 3.12. Desde esta carpeta:

```bash
python -m pip install -r requirements.txt
python validar_instancia.py
python -m streamlit run app.py
```

## Alcance

El caso base usa la matriz publicada en `MODELO PL` y CBC mediante PuLP.
La reconstrucción desde las hojas `Datos M1` a `Datos M10` es un análisis diferente.
La pestaña Monte Carlo distingue la referencia histórica agregada de cualquier ejecución nueva.
La simulación de 1000 escenarios puede sobrepasar los recursos o límites de tiempo del alojamiento gratuito.

## Privacidad

El Excel incluye información operativa. Crear el repositorio como privado y autorizar expresamente a quienes deban acceder a la aplicación. Antes de hacer público el código o la app, revisar el Excel y las salidas visibles.
