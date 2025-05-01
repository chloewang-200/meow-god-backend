from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import auth, initialize_app, credentials, firestore
from google.cloud import firestore
from functools import wraps
from dotenv import load_dotenv
import os
from google.oauth2 import service_account
from flask_cors import CORS
# ✅ Initialize Firebase Admin with default credentials (Cloud Run safe)
# initialize_app()

SERVICE_ACCOUNT_FILE = "serviceAccountKey.json"

USE_LOCAL = os.getenv("USE_LOCAL", "false").lower() == "true"

# 🔐 Initialize Firebase
if USE_LOCAL:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
    db = firestore.Client(credentials=cred, project=cred.project_id)
else:
    firebase_admin.initialize_app()
    db = firestore.Client()


app = Flask(__name__)
CORS(app, supports_credentials=True, resources={r"/*": {
    "origins": "*",
    "allow_headers": ["Authorization", "Content-Type"],
    "methods": ["GET", "POST", "OPTIONS"]
}})


# 🔐 Middleware: verify Firebase ID token
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Unauthorized"}), 401
        id_token = auth_header.split(" ")[1]
        try:
            decoded_token = auth.verify_id_token(id_token)
            print(decoded_token)
            request.uid = decoded_token["uid"]
            print(request.uid)
            return f(*args, **kwargs)
        except Exception as e:
            print("Invalid or expired token", e)
            return jsonify({"error": "Invalid or expired token"}), 401
    return decorated

# 🔄 Helper to get Firestore document reference
def get_user_ref(uid):
    return db.collection("users").document(uid)

# 📘 Get balance
@app.route("/balance", methods=["GET"])
@require_auth
def get_balance():
    uid = request.uid
    doc = get_user_ref(uid).get()
    if not doc.exists:
        return jsonify({"balance": 0.0})
    return jsonify({"balance": doc.to_dict().get("balance", 0.0)})

# ➕ Add to balance
@app.route("/balance/add", methods=["POST"])
@require_auth
def add_balance():
    uid = request.uid
    amount = float(request.json.get("amount", 0.0))
    user_ref = get_user_ref(uid)
    user_ref.set({"balance": firestore.Increment(amount)}, merge=True)
    return jsonify({"message": f"Added {amount} to balance"})

# ➖ Deduct from balance
@app.route("/balance/deduct", methods=["POST"])
@require_auth
def deduct_balance():
    uid = request.uid
    amount = float(request.json.get("amount", 0.0))
    user_ref = get_user_ref(uid)
    doc = user_ref.get()
    current_balance = doc.to_dict().get("balance", 0.0)
    if current_balance < amount:
        return jsonify({"error": "Insufficient balance"}), 400
    user_ref.set({"balance": current_balance - amount}, merge=True)
    return jsonify({"message": f"Deducted {amount} from balance"})

if __name__ == "__main__":
    app.run(debug=True)
