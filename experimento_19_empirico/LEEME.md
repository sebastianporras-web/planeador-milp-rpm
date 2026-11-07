# Cómo ejecutar el conjunto nuevo

Este módulo añade un estudio de cien instancias, separado del factorial de 144 y de la app. No borra archivos ni resultados anteriores.

1. Abrir Actions → Estudio 100 instancias sinteticas de ventas.
2. Ejecutar con alcance verificar. Publica empirico100-entradas-...; no necesita WLS para generar entradas y probar CBC/HiGHS con casos artificiales.
3. Revisar protocolo_generacion.json, las cien huellas y distribucion_estratos.csv. La naturaleza es sintética transversal; no es un histórico diario.
4. Ejecutar piloto. La licencia WLS se comprueba sin mostrar credenciales. El informe parcial tendrá 4 de 400 registros; es esperado.
5. Tras revisar el piloto, ejecutar completo una sola vez. Aparecerán diez bloques. Cada instancia se resuelve con la heurística, CBC, HiGHS y Gurobi sin solución heredada, con 180 s y dos hilos por motor.
6. Descargar el informe y los diez bloques. El informe completo debe contener 400 registros. Las soluciones no certificadas, inviabilidades y fallos permanecen identificados.

No usar Volver a ejecutar todos los trabajos para iniciar el conjunto completo desde un piloto: eso repite el mismo alcance. Usar Ejecutar flujo de trabajo y seleccionar completo.

Los Secrets existentes WLSACCESSID, WLSSECRET y LICENSEID siguen en GitHub; no se copian al código ni se comparten. La app mantiene su configuración operativa. Las dependencias experimentales permanecen fijadas en experimento_19/requirements.txt.

El protocolo describe el supuesto de intercambio entre referencias del mismo estrato. La falta de fechas no se soluciona inventando ventas. La aceptación académica de ese alcance corresponde al director. El issue no se cierra antes de auditar resultados y ajustar la tesis y la presentación.
