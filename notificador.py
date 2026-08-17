import os
import json
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import firebase_admin
from firebase_admin import credentials, messaging, firestore

# ============================================================
# TRUCO PARA RENDER (Web Service Free)
# Servidor HTTP para satisfacer la comprobación de puerto y aceptar POST
# ============================================================
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Servicio Notificador ESP32 Activo en Render")

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        try:
            datos = json.loads(post_data.decode('utf-8'))
            fecha = datos.get('fecha_hora', datos.get('Fecha_Hora', 'Hora no registrada'))
            dispositivo_id = datos.get('dispositivo_id', 'Desconocido')
            
            print(f"\n[!] ¡ALERTA RECIBIDA POR POST DE ESP32! ID: {dispositivo_id} ({fecha})")
            
            # 1. Registrar la Alerta en Firestore (para el Historial de la App)
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

            # 2. Despachar Notificación Push de Alta Prioridad a Google FCM
            print(" -> Despachando Notificación Push a Google FCM...")
            mensaje = messaging.Message(
                topic='movimiento',
                notification=messaging.Notification(
                    title='¡ALERTA DE SEGURIDAD!',
                    body=f'Movimiento detectado: {fecha}'
                ),
                android=messaging.AndroidConfig(
                    priority='high',
                    notification=messaging.AndroidNotification(
                        sound='alarma',
                        channel_id='canal_alarmas_pir',
                        priority='max'
                    )
                )
            )

            respuesta = messaging.send(mensaje)
            print(f" -> ¡Notificación Push enviada con éxito! ID: {respuesta}")

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

    # Silenciar logs HTTP en consola para no llenar el historial de Render
    def log_message(self, format, *args):
        return

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    print(f">>> [SERVIDOR WEB] Escuchando en el puerto {port} para Render. <<<")
    server.serve_forever()

# Iniciar servidor web en segundo plano
threading.Thread(target=run_web_server, daemon=True).start()
# ============================================================

# 1. Obtener Credenciales de Firebase desde la Variable de Entorno o un Archivo Local
creds_env = os.environ.get('FIREBASE_CREDENTIALS_JSON')

if creds_env:
    # Carga desde Variable de Entorno (Modo Nube / Servidor)
    cred_dict = json.loads(creds_env)
    cred = credentials.Certificate(cred_dict)
    print(">>> [NOTIFICADOR] Cargando credenciales de Firebase desde Variable de Entorno. <<<")
else:
    # Carga desde Archivo Local (Modo Desarrollo / Local)
    ruta_local = 'clave_firebase.json'
    if os.path.exists(ruta_local):
        cred = credentials.Certificate(ruta_local)
        print(">>> [NOTIFICADOR] Cargando credenciales de Firebase desde 'clave_firebase.json'. <<<")
    else:
        raise ValueError("Error: No se encontraron las credenciales de Firebase en variables de entorno ni en archivo local.")

firebase_admin.initialize_app(cred)
db = firestore.client()

print("=" * 60)
print("  SERVICIO DE NOTIFICACIONES PUSH ACTIVO - MODO NUBE / SPARK")
print("  Esperando peticiones POST del ESP32...")
print("=" * 60)

# Mantener el proceso vivo 24/7
while True:
    try:
        time.sleep(1)
    except KeyboardInterrupt:
        print("\n>>> [NOTIFICADOR] Deteniendo el servicio... <<<")
        break
    except Exception as e:
        print(f">>> [NOTIFICADOR] Ocurrió un error inesperado en el bucle principal: {e} <<<")
        time.sleep(5)
