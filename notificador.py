import os
import json
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import firebase_admin
from firebase_admin import credentials, messaging, firestore

# ============================================================
# TRUCO PARA RENDER (Web Service Free)
# Abre un servidor HTTP dummy para satisfacer la comprobación de puerto
# ============================================================
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Servicio Notificador ESP32 Activo en Render")

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
print("  Monitoreando la Colección 'alertas' en Tiempo Real...")
print("=" * 60)

# Variable para ignorar Alertas Antiguas Cargadas al Iniciar
escucha_inicial = True

def al_recibir_alerta(doc_snapshot, changes, read_time):
    global escucha_inicial
    
    # En la primera carga ignoramos los documentos existentes para no duplicar alertas viejas
    if escucha_inicial:
        escucha_inicial = False
        return

    for change in changes:
        # Solo reaccionamos cuando el ESP32 inserta un Documento NUEVO
        if change.type.name == 'ADDED':
            doc = change.document
            datos = doc.to_dict()
            fecha = datos.get('Fecha_Hora', 'Hora no registrada')
            
            print(f"\n[!] ¡NUEVO MOVIMIENTO DETECTADO POR ESP32! ({fecha})")
            print(" -> Despachando Notificación Push a Google FCM...")

            # Construcción del Mensaje Push de Alta Prioridad
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

            try:
                respuesta = messaging.send(mensaje)
                print(f" -> ¡Notificación Push enviada con éxito! ID: {respuesta}")
            except Exception as e:
                print(f" -> Error al enviar Notificación Push: {e}")

# Escuchar la Colección 'alertas' en Tiempo Real
col_query = db.collection('alertas')
query_watch = col_query.on_snapshot(al_recibir_alerta)

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
