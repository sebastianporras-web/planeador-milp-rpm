"""Lectura de evidencia histórica; no genera ni reemplaza resultados."""
import json
import math
from pathlib import Path

NUMERICOS = ('media_pct', 'mediana_pct', 'sd_pct', 'se_pct',
             'ci95_low_pct', 'ci95_high_pct', 'min_pct', 'max_pct')

def validar_referencia(data):
    if not isinstance(data, dict):
        raise ValueError('La referencia debe ser un objeto JSON.')
    for key in ('n', 'positive_count'):
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f'{key} debe ser un entero.')
    if data['n'] <= 0 or not 0 <= data['positive_count'] <= data['n']:
        raise ValueError('Conteos históricos inconsistentes.')
    for key in NUMERICOS:
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f'{key} debe ser numérico y finito.')
    if data['sd_pct'] < 0 or data['se_pct'] < 0:
        raise ValueError('La dispersión no puede ser negativa.')
    if not data['min_pct'] <= data['media_pct'] <= data['max_pct']:
        raise ValueError('La media está fuera del rango histórico.')
    if not data['min_pct'] <= data['mediana_pct'] <= data['max_pct']:
        raise ValueError('La mediana está fuera del rango histórico.')
    if data['ci95_low_pct'] > data['ci95_high_pct']:
        raise ValueError('Los extremos del intervalo están invertidos.')
    if not isinstance(data.get('methodology_note'), str) or not data['methodology_note'].strip():
        raise ValueError('Falta la nota de metodología.')
    return data

def leer_referencia(directorio=None):
    """Ruta relativa al código, no al directorio desde el que se ejecuta Python."""
    root = Path(directorio) if directorio is not None else Path(__file__).resolve().parent
    path = root / 'monte_carlo_reference.json'
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    return validar_referencia(data)
