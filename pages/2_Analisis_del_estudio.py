"""Conserva los análisis históricos, separados del contrato de carga operativa."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).resolve().parents[1] / 'analisis_tesis.py'), run_name='__main__')
