from flask import Flask, request, jsonify
import os

app = Flask(__name__)

@app.route("/webhook/syonet/lead", methods=["POST"])
def receive_lead():
    try:
        # Intentar JSON primero
        data = request.get_json(silent=True)

        if data is None:
            # Si no hay JSON, intentar leer form-data o raw body
            data = request.form.to_dict()  # si envían x-www-form-urlencoded
            if not data:
                # Si no hay form-data, leer el body crudo
                raw = request.data.decode('utf-8')
                return jsonify({
                    "msg": "Datos recibidos pero no eran JSON ni form-data",
                    "raw_data": raw
                }), 400

        print("Lead recibido:", data)
        return jsonify({
            "msg": "Lead recibido correctamente",
            "lead": data
        }), 200

    except Exception as e:
        import traceback
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
