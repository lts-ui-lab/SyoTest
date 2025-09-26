import json
import time
import requests
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import or_

app = Flask(__name__)

# Configuración de SQLite (Render)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///leads.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# Configuración Syonet
SYONET_BASE = "https://demomex.syonet.com/api"
   # Credenciales de Syonet
        usuario = "RODRIGO.SANTIAGO"
        password = "Syonet01#"
        auth = base64.b64encode(f"{usuario}:{password}".encode()).decode()
AUTH_HEADER = {
    "Content-Type": "application/json",
    "Authorization": "Basic " + auth
}

# Modelo de Lead
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

# Webhook para recibir leads desde Syonet
@app.route("/webhook/syonet/lead", methods=["POST"])
def receive_lead():
    try:
        data = request.get_json()

        # Caso: JSON anidado en clave
        if isinstance(data, dict) and len(data) == 1:
            raw_json = list(data.keys())[0]
            lead_data = json.loads(raw_json)
        else:
            lead_data = data

        print("Lead procesado:", lead_data)

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

        # Programar cita automáticamente (ejemplo: mañana a las 10:00)
        fecha_cita = int(time.mktime(datetime.strptime(
            "2025-09-30 10:00", "%Y-%m-%d %H:%M").timetuple()) * 1000)

        payload = {
            "tipo": "VISITA LOJA",
            "resultado": "AGENDADA",
            "conclusao": f"Cita programada para {nuevo_lead.nombre_cliente}",
            "dataHoraAcao": fecha_cita,
            "testDrive": False
        }

        r = requests.post(
            f"{SYONET_BASE}/evento/{id_evento}/acao",
            headers=AUTH_HEADER,
            json=payload
        )

        return jsonify({
            "msg": "Lead recibido, almacenado y cita agendada",
            "lead": nuevo_lead.to_dict(),
            "syonet_response": r.json()
        }), 200

    except Exception as e:
        return jsonify({
            "msg": "Error al procesar el lead",
            "error": str(e)
        }), 500

# Endpoint para listar leads
@app.route("/leads", methods=["GET"])
def list_leads():
    leads = Lead.query.order_by(Lead.fecha_recepcion.desc()).all()
    return jsonify([lead.to_dict() for lead in leads]), 200

# Endpoint de búsqueda flexible
@app.route("/leads/search", methods=["GET"])
def search_leads():
    nombre = request.args.get("nombre")
    telefono = request.args.get("telefono")
    email = request.args.get("email")
    id_evento = request.args.get("id_evento")

    query = Lead.query

    if id_evento:
        query = query.filter(Lead.id_evento == id_evento)
    if nombre:
        query = query.filter(Lead.nombre_cliente.ilike(f"%{nombre}%"))
    if telefono:
        query = query.filter(Lead.telefono.ilike(f"%{telefono}%"))
    if email:
        query = query.filter(Lead.email.ilike(f"%{email}%"))

    results = query.order_by(Lead.fecha_recepcion.desc()).all()

    if not results:
        return jsonify({"msg": "No se encontraron leads con esos criterios"}), 404

    return jsonify([lead.to_dict() for lead in results]), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
