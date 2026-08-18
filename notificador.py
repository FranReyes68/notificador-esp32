import os
import json
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import firebase_admin
from firebase_admin import credentials, messaging, firestore

# ============================================================
# TRUCO PARA RENDER (Web Service Free)
# Servidor HTTP en segundo plano para satisfacer la comprobación de Puerto (Health Check)
# y aceptar peticiones POST provenientes del Dispositivo ESP32.
# ============================================================
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    
    def do_GET(self):
        """Endpoint de verificación de estado (Health Check) requerido por Render para mantener el servicio activo."""
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Servicio Notificador ESP32 Activo en Render")

    def do_POST(self):
        """Webhook principal que recibe las alertas de intrusión enviadas por el ESP32 mediante HTTP POST."""
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            datos = json.loads(post_data.decode('utf-8'))
            fecha = datos.get('fecha_hora', datos.get('Fecha_Hora', 'Hora no registrada'))
            dispositivo_id = datos.get('dispositivo_id', 'Desconocido')
            
            print(f"\n[!] ¡ALERTA RECIBIDA POR POST DE ESP32! ID: {dispositivo_id} ({fecha})")
            
            # 1. Registrar la Alerta en Firestore (Almacena el Historial persistente para la Interfaz de Flutter)
            try:
                db.collection('alertas').add({
                    'Dispositivo_ID': dispositivo_id,
                    'Fecha_Hora': fecha,
                    'Evento': 'Movimiento detectado',
                    'Timestamp': firestore.SERVER_TIMESTAMP
                })
                print(" -> ¡Alerta registrada exitosamente en Firestore!")
            except Exception as db_err:
                print(f" -> Error al guardar en Firestore: {db_err}")

            # 2. Despachar Notificación Push de Alta Prioridad a Google FCM (Enfoque basado en Tópicos para la App)
            print(" -> Despachando Notificación Push a Google FCM...")
            mensaje = messaging.Message(
                topic='movimiento', # Tópico al cual se suscriben los dispositivos móviles
                data={
                    'title': '¡ALERTA DE SEGURIDAD!',
                    'body': f'Movimiento detectado: {fecha}',
                    'dispositivo_id': str(dispositivo_id)
                },
                android=messaging.AndroidConfig(
                    priority='high' # Prioridad alta para forzar activación inmediata en Android
                )
            )

            respuesta = messaging.send(mensaje)
            print(f" -> ¡Notificación Push enviada con éxito! ID: {respuesta}")

            # Responder al ESP32 con confirmación HTTP 200 OK y metadatos de FCM
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "fcm_id": respuesta}).encode('utf-8'))

        except Exception as e:
            print(f" -> Error general procesando POST: {e}")
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

    def log_message(self, format, *args):
        """Silencia los logs estándar de peticiones HTTP en consola para evitar saturar el Historial de Registros en Render."""
        return

def run_web_server():
    """Configura y arranca el Servidor HTTP escuchando en el Puerto asignado por Render (o 10000 por defecto)."""
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    print(f">>> [SERVIDOR WEB] Escuchando en el puerto {port} para Render. <<<")
    server.serve_forever()

# Inicializar y ejecutar el Servidor Web de forma concurrente en un hilo en segundo plano
threading.Thread(target=run_web_server, daemon=True).start()
# ============================================================

# Gestión de Credenciales de Firebase: Soporte dual para Entorno Cloud (Render) o Desarrollo Local
creds_env = os.environ.get('FIREBASE_CREDENTIALS_JSON')

if creds_env:
    # Carga desde Variable de Entorno (Modo Producción en Servidor Nube)
    cred_dict = json.loads(creds_env)
    cred = credentials.Certificate(cred_dict)
    print(">>> [NOTIFICADOR] Cargando credenciales de Firebase desde Variable de Entorno. <<<")
else:
    # Carga desde Archivo Local (Modo Pruebas / Desarrollo Local)
    ruta_local = 'clave_firebase.json'
    if os.path.exists(ruta_local):
        cred = credentials.Certificate(ruta_local)
        print(">>> [NOTIFICADOR] Cargando credenciales de Firebase desde 'clave_firebase.json'. <<<")
    else:
        raise ValueError("Error: No se encontraron las credenciales de Firebase en variables de entorno ni en archivo local.")

# Inicialización formal del SDK de Admin de Firebase y cliente de Firestore
firebase_admin.initialize_app(cred)
db = firestore.client()

print("=" * 60)
print("  SERVICIO DE NOTIFICACIONES PUSH ACTIVO - MODO NUBE / SPARK")
print("  Esperando peticiones POST del ESP32...")
print("=" * 60)

# Bucle Principal de Control para mantener el proceso vivo 24/7 de manera resiliente
while True:
    try:
        time.sleep(1)
    except KeyboardInterrupt:
        print("\n>>> [NOTIFICADOR] Deteniendo el servicio... <<<")
        break
    except Exception as e:
        print(f">>> [NOTIFICADOR] Ocurrió un error inesperado en el bucle principal: {e} <<<")
        time.sleep(5)
