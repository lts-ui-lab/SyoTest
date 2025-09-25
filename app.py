from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/webhook/syonet/lead", methods=["POST"])
def receive_lead():
    try:
        data = request.get_json()
        print("Lead recibido:", data)
        return jsonify({
            "msg": "Lead recibido correctamente",
            "lead": data
        }), 200
    except Exception as e:
        return jsonify({
            "msg": "Error al procesar el lead",
            "error": str(e)
        }), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
