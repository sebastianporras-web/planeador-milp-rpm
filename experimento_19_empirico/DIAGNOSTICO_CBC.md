# Diagnóstico del intento histórico I045/CBC

Fuente: corrida 42319546329, artefacto estudio19-bloque-4-42319546329, descargado directamente mediante el acceso autenticado de GitHub. El ZIP coincide con la huella publicada 47102e5674b16240bfe0fdfce039c2aa452b7c0c78039a06b4bf0b933ac4d989.

El resultado original declara PulpSolverError y 5,221847 segundos totales, con presupuesto interno de 180 segundos. El log contiene SIGABRT y una traza en CbcHeuristicFPump, smallBranchAndBound y ClpSimplexDual. El registro corresponde a una terminación anómala nativa, no a una prueba de inviabilidad ni a una parada normal por tiempo. Los archivos históricos no se reemplazan.

El protocolo del conjunto nuevo desactiva Feasibility Pump para todas sus instancias. El resto de heurísticas, el presolve y los cortes declarados permanecen activos. El puente conserva código de retorno, comando y archivo MPS. Un error nativo seguirá apareciendo como error.

Una prueba técnica local sobre la entrada original I045, con dos hilos, sin inicio heredado y un presupuesto interno de 20 segundos, terminó con retorno cero y un plan factible sin certificado. El ejecutor midió 30,598558 segundos totales, que incluyen preparación y cierre. Esta prueba comprueba la ruta alternativa en ese entorno; no garantiza ausencia de todos los fallos nativos ni sustituye el resultado histórico o las resoluciones finales de 180 segundos.
