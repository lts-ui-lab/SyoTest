import os
import json
import time
import base64
import requests
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

# Función para llamar al lead vía Twilio
def llamar_lead(numero_telefono, mensaje="Hola, esta es una confirmación de tu cita."):
    try:
        call = twilio_client.calls.create(
            to=numero_telefono,
            from_=TWILIO_NUMBER,
            twiml=f'<Response><Say>{mensaje}</Say></Response>'
        )
        return {"status": "ok", "sid": call.sid}
    except Exception as e:
        return {"status": "error", "error": str(e)}

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
                lead_data = data  # fallback si no es JSON válido

        print("Lead recibido:", lead_data)

        # Extraer datos importantes
        id_evento = lead_data.get("idEvento")
        cliente = lead_data.get("cliente", {})
        evento = lead_data.get("event", {})

        nuevo_lead = Lead(
            id_evento=id_evento,
            nombre_cliente=cliente.get("nome") or cliente.get("name"),
            email=cliente.get("email"),
            telefono=cliente.get("ddiCel") or cliente.get("telefone"),
            event_group=evento.get("eventGroup"),
            event_type=evento.get("eventType"),
            comentario=evento.get("comment")
        )

        db.session.add(nuevo_lead)
        db.session.commit()

        # Fecha de cita: mañana a las 10:00
        manana = datetime.now() + timedelta(days=1)
        fecha_cita = int(time.mktime(
            manana.replace(hour=10, minute=0, second=0, microsecond=0).timetuple()
        ) * 1000)

        payload = {
            "tipo": "VISITA LOJA",
            "resultado": "AGENDADA",
            "conclusao": f"Cita programada para {nuevo_lead.nombre_cliente}",
            "dataHoraAcao": fecha_cita,
            "testDrive": False
        }

        # Llamada a la API de Syonet
        try:
            r = requests.post(
                f"{SYONET_BASE}/evento/{id_evento}/acao",
                headers=AUTH_HEADER,
                json=payload,
                timeout=10
            )
            try:
                syonet_response = r.json()
            except Exception:
                syonet_response = {"status_code": r.status_code, "text": r.text}
        except requests.RequestException as e:
            syonet_response = {"error": str(e)}

        # Llamada al lead vía Twilio (opcional)
        if nuevo_lead.telefono:
            resultado_llamada = llamar_lead(
                nuevo_lead.telefono,
                mensaje=f"Hola {nuevo_lead.nombre_cliente}, tu cita ha sido agendada para mañana a las 10:00."
            )
        else:
            resultado_llamada = {"status": "no_number"}

        return jsonify({
            "msg": "Lead recibido, almacenado, cita agendada y llamada realizada",
            "lead": nuevo_lead.to_dict(),
            "syonet_response": syonet_response,
            "llamada": resultado_llamada
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "msg": "Error al procesar el lead",
            "error": str(e)
        }), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

