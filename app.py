import os 
import json
import time
import base64
import requests
import threading
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from twilio.rest import Client

app = Flask(__name__)

# Configuración de SQLite
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///leads.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# Configuración Syonet
SYONET_BASE = os.getenv("SYONET_BASE", "https://demomex.syonet.com/api")
SYONET_USER = os.getenv("SYONET_USER", "RODRIGO.SANTIAGO")
SYONET_PASS = os.getenv("SYONET_PASS", "Syonet01#")

auth = base64.b64encode(f"{SYONET_USER}:{SYONET_PASS}".encode()).decode()
AUTH_HEADER = {
    "Content-Type": "application/json",
    "Authorization": f"Basic {auth}"
}

# Configuración Twilio
TWILIO_SID = os.getenv("TWILIO_SID", "ACcf61098091aa930787fba3203ba2585e")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN", "9d7e8d892451ba6d9983cee88fd7ee31")
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER", "+15304288284")
twilio_client = Client(TWILIO_SID, TWILIO_TOKEN)

# Modelo Lead
class Lead(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_evento = db.Column(db.Integer, nullable=False)
    nombre_cliente = db.Column(db.String(255))
    email = db.Column(db.String(255))
    telefono = db.Column(db.String(50))
    event_group = db.Column(db.String(50))
    event_type = db.Column(db.String(50))
    comentario = db.Column(db.Text)
    fecha_recepcion = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "id_evento": self.id_evento,
            "nombre_cliente": self.nombre_cliente,
            "email": self.email,
            "telefono": self.telefono,
            "event_group": self.event_group,
            "event_type": self.event_type,
            "comentario": self.comentario,
            "fecha_recepcion": self.fecha_recepcion.isoformat()
        }

# Inicializar DB
with app.app_context():
    db.create_all()

# Función para procesar el lead de forma asincrónica
def procesar_lead_async(lead_id):
    with app.app_context():
        lead = Lead.query.get(lead_id)
        if not lead:
            print(f"[DEBUG] Lead {lead_id} no encontrado.")
            return

        if not lead.telefono:
            print(f"[DEBUG] Lead {lead.id} no tiene teléfono, no se puede contactar ni agendar.")
            return

        print(f"[DEBUG] Procesando Lead {lead.id}: {lead.nombre_cliente}, Tel: {lead.telefono}")

        # Intentar llamada
        contacto_exitoso = False
        try:
            call = twilio_client.calls.create(
                to=lead.telefono,
                from_=TWILIO_NUMBER,
                twiml=f'<Response><Say>Hola {lead.nombre_cliente}, tu cita ha sido agendada para mañana a las 10:00.</Say></Response>'
            )
            print(f"[DEBUG] Llamada realizada con SID: {call.sid}")
            contacto_exitoso = True
        except Exception as e_call:
            print(f"[DEBUG] Error en la llamada: {e_call}")

        # Intentar WhatsApp si falla llamada
        if not contacto_exitoso:
            try:
                msg_whatsapp = twilio_client.messages.create(
                    to=f"whatsapp:{lead.telefono}",
                    from_=f"whatsapp:{TWILIO_NUMBER}",
                    body=f"Hola {lead.nombre_cliente}, no pudimos llamarte. Tu cita sigue agendada para mañana a las 10:00."
                )
                print(f"[DEBUG] WhatsApp enviado con SID: {msg_whatsapp.sid}")
                contacto_exitoso = True
            except Exception as e_whatsapp:
                print(f"[DEBUG] Error en WhatsApp: {e_whatsapp}")

        # Intentar SMS si falla WhatsApp
        if not contacto_exitoso:
            try:
                msg_sms = twilio_client.messages.create(
                    to=lead.telefono,
                    from_=TWILIO_NUMBER,
                    body=f"Hola {lead.nombre_cliente}, no pudimos llamarte ni enviarte WhatsApp. Tu cita sigue agendada para mañana a las 10:00."
                )
                print(f"[DEBUG] SMS enviado con SID: {msg_sms.sid}")
                contacto_exitoso = True
            except Exception as e_sms:
                print(f"[DEBUG] Error en SMS: {e_sms}")

        # Solo agendar en Syonet si hubo contacto exitoso
        if contacto_exitoso:
            manana = datetime.now() + timedelta(days=1)
            fecha_cita = int(time.mktime(
                manana.replace(hour=10, minute=0, second=0, microsecond=0).timetuple()
            ) * 1000)

            payload = {
                "tipo": "VISITA LOJA",
                "resultado": "AGENDADA",
                "conclusao": f"Cita programada para {lead.nombre_cliente}",
                "dataHoraAcao": fecha_cita,
                "testDrive": False
            }

            try:
                r = requests.post(
                    f"{SYONET_BASE}/evento/{lead.id_evento}/acao",
                    headers=AUTH_HEADER,
                    json=payload,
                    timeout=10
                )
                try:
                    syonet_response = r.json()
                except Exception:
                    syonet_response = {"status_code": r.status_code, "text": r.text}

                print(f"[DEBUG] Cita agendada en Syonet: {syonet_response}")
            except requests.RequestException as e_syonet:
                print(f"[DEBUG] Error al agendar cita en Syonet: {e_syonet}")
        else:
            print(f"[DEBUG] No se pudo contactar al lead {lead.id}. No se agenda cita.")

# Webhook para recibir leads
@app.route("/webhook/syonet/lead", methods=["POST"])
def receive_lead():
    try:
        data = request.get_json(force=True)

        # Manejo de JSON anidado
        lead_data = data
        if isinstance(data, dict) and len(data) == 1:
            try:
                raw_json = list(data.keys())[0]
                lead_data = json.loads(raw_json)
            except Exception:
                lead_data = data  # fallback

        # Extraer datos importantes
        id_evento = lead_data.get("idEvento")
        cliente = lead_data.get("cliente", {})
        evento = lead_data.get("event", {})
        telefonos = cliente.get("phones", [])
        telefono_formateado = None

        if telefonos:
            tel_obj = telefonos[0]
            ddi = tel_obj.get("ddi", "")
            numero = tel_obj.get("numero", "")
            if ddi and numero:
                telefono_formateado = f"+{ddi}{numero}"

        nuevo_lead = Lead(
            id_evento=id_evento,
            nombre_cliente=cliente.get("nome") or cliente.get("name"),
            email=cliente.get("email"),
            telefono=telefono_formateado,
            event_group=evento.get("eventGroup"),
            event_type=evento.get("eventType"),
            comentario=evento.get("comment")
        )

        db.session.add(nuevo_lead)
        db.session.commit()

        # Procesar de forma asincrónica (llamada, WhatsApp o SMS)
        threading.Thread(target=procesar_lead_async, args=(nuevo_lead.id,)).start()

        # Siempre devolver 200 OK inmediatamente
        return jsonify({"msg": "Lead recibido y en proceso"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "msg": "Error al procesar el lead",
            "error": str(e)
        }), 200  # <-- devolver 200 para que Syonet no marque error

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
