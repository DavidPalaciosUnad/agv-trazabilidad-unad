# Manual de operación (versión prototipo)

## Antes de operar
1. Verificar que la cinta guía esté limpia y sin despegues, con curvas de radio ≥ 1 m.
2. Verificar la carga de la batería (≥ 15 %) y el funcionamiento de la seta de emergencia.
3. Delimitar y señalizar el pasillo de circulación del AGV.

## Operación normal
1. Iniciar el módulo de gestión (`python -m gestion.app`) y abrir la interfaz web.
2. Registrar la orden: origen, destino, masa (≤ 50 kg), prioridad y código del solicitante (nunca el nombre).
3. Cargar el material cuando el AGV se detenga en el origen (permanencia de 4 s en el prototipo).
4. Retirar el material en el destino. La orden queda COMPLETADA y trazada.

## Situaciones especiales
- **Persona u obstáculo en la trayectoria**: el AGV reduce a 0,2 m/s a 1,2 m y se detiene a 0,5 m; reanuda solo tras 2 s de paso libre.
- **Emergencia**: presionar la seta roja. Para reanudar: liberar la seta y presionar el pulsador verde de rearme (o el botón «Rearme manual» de la interfaz).
- **Pérdida de red**: el AGV continúa a velocidad reducida y lo indica con la luz ámbar.

## Mantenimiento
Revisar semanalmente la cinta guía, el estado de las ruedas, el apriete de la estructura y la batería; exportar mensualmente la bitácora (CSV) como evidencia para el SG-SST.
