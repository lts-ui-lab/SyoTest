from flask import Flask, request, jsonify
import os
import traceback

app = Flask(__name__)

@app.route("/webhook/syonet/lead", methods=["POST"])
def receive_lead():
    try:
        # Intentamos obtener JSON del request
        data = request.get_json(silent=True)
        if data is None:
            # Si no se envió JSON válido
            return jsonify({
                "msg": "JSON inválido o no enviado",
                "received_data": request.data.decode('utf-8')
            }), 400

        # Aquí puedes procesar el lead como necesites
        print("Lead recibido:", data)

        return jsonify({
            "msg": "Lead recibido correctamente",
            "lead": data
        }), 200

    except Exception as e:
        # Captura cualquier excepción para no devolver 500
        traceback_str = traceback.format_exc()
        print("Error al procesar el lead:", traceback_str)
        return jsonify({
            "msg": "Error al procesar el lead",
            "error": str(e),
            "traceback": traceback_str
        }), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
