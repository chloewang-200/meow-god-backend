from flask import Flask, request, jsonify
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, auth
from sqlalchemy import create_engine, Column, String, Float, Integer, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
from sqlalchemy import DateTime
from datetime import datetime
from firebase_admin import firestore
import json


# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app, resources={
    r"/*": {
        "origins": "*",  # In production, replace with your frontend domain
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }
})

# Initialize Firebase Admin
def initialize_firebase():
    try:
        print("Starting Firebase initialization...")
        print("Environment variables available:")
        for key in ['FIREBASE_PRIVATE_KEY_ID', 'FIREBASE_CLIENT_EMAIL', 'FIREBASE_CLIENT_ID', 'FIREBASE_CLIENT_CERT_URL']:
            value = os.getenv(key)
            print(f"{key}: {'Set' if value else 'Not set'}")
        print("FIREBASE_PRIVATE_KEY: " + ('Set' if os.getenv('FIREBASE_PRIVATE_KEY') else 'Not set'))
        
        # For local development
        if os.path.exists("serviceAccountKey.json"):
            print("Using local serviceAccountKey.json")
            cred = credentials.Certificate("serviceAccountKey.json")
        # For Cloud Run
        else:
            print("Using environment variables for Firebase credentials")
            # Get credentials from environment variables
            private_key = os.getenv('FIREBASE_PRIVATE_KEY')
            if not private_key:
                raise ValueError("FIREBASE_PRIVATE_KEY environment variable is not set")
            
            print("Private key found, formatting...")
            # Handle the private key format
            private_key = private_key.replace('\\n', '\n')
            if not private_key.startswith('-----BEGIN PRIVATE KEY-----'):
                private_key = '-----BEGIN PRIVATE KEY-----\n' + private_key
            if not private_key.endswith('-----END PRIVATE KEY-----'):
                private_key = private_key + '\n-----END PRIVATE KEY-----'
            
            print("Creating credentials object...")
            cred = credentials.Certificate({
                "type": "service_account",
                "project_id": "meow-god",
                "private_key_id": os.getenv('FIREBASE_PRIVATE_KEY_ID'),
                "private_key": private_key,
                "client_email": os.getenv('FIREBASE_CLIENT_EMAIL'),
                "client_id": os.getenv('FIREBASE_CLIENT_ID'),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_x509_cert_url": os.getenv('FIREBASE_CLIENT_CERT_URL')
            })
        
        print("Initializing Firebase Admin SDK...")
        # Initialize Firebase Admin SDK
        app = firebase_admin.initialize_app(cred)
        print("Firebase Admin SDK initialized successfully")
        return app
    except Exception as e:
        print(f"Error initializing Firebase: {e}")
        import traceback
        print("Full traceback:", traceback.format_exc())
        return None

# Initialize Firebase first
app = initialize_firebase()
if not app:
    raise Exception("Failed to initialize Firebase")

# Initialize Firestore client AFTER Firebase Admin initialization
print("Initializing Firestore client...")
db = firestore.client()
print("Firestore client initialized successfully")

# Database setup
engine = create_engine('sqlite:///users.db')
Base = declarative_base()
Session = sessionmaker(bind=engine)

# Item model
class Item(Base):
    __tablename__ = 'items'
    
    id = Column(Integer, primary_key=True)
    user_uid = Column(String)
    item_id = Column(Integer)  # The integer representing the item
    category = Column(String)  # The category of the item (candle, food, vase, etc.)
    x = Column(String)  # x position (changed to String to store percentage)
    y = Column(String)  # y position (changed to String to store percentage)

# User model
class User(Base):
    __tablename__ = 'users'
    
    uid = Column(String, primary_key=True)
    balance = Column(Float, default=0.0)
    candle_start_time = Column(DateTime, nullable=True)

# Create tables
Base.metadata.create_all(engine)

def verify_token(token):
    if token.startswith("Bearer "):
        token = token.split(" ")[1]  # strip 'Bearer '
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        print("Token verification failed:", e)
        return None


@app.route('/balance', methods=['GET'])
def get_balance():
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'error': 'No token provided'}), 401
    
    decoded_token = verify_token(token)
    if not decoded_token:
        return jsonify({'error': 'Invalid token'}), 401
    
    # Get balance from Firestore
    user_doc = db.collection('users').document(decoded_token['uid']).get()
    firestore_balance = user_doc.get('balance') if user_doc.exists else 0.0
    
    session = Session()
    user = session.query(User).filter_by(uid=decoded_token['uid']).first()
    
    if not user:
        user = User(uid=decoded_token['uid'], balance=firestore_balance)
        session.add(user)
        session.commit()
    else:
        # Update SQLite balance if it differs from Firestore
        if user.balance != firestore_balance:
            user.balance = firestore_balance
            session.commit()
    
    balance = user.balance
    session.close()
    return jsonify({'balance': balance})

@app.route('/balance/add', methods=['POST'])
def add_balance():
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'error': 'No token provided'}), 401
    
    decoded_token = verify_token(token)
    if not decoded_token:
        return jsonify({'error': 'Invalid token'}), 401
    
    amount = request.json.get('amount')
    if not amount or amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400
    
    session = Session()
    user = session.query(User).filter_by(uid=decoded_token['uid']).first()
    
    if not user:
        user = User(uid=decoded_token['uid'], balance=0.0)
        session.add(user)
        session.commit()

        # Write initial record to Firestore
        db.collection('users').document(user.uid).set({
            'balance': 0.0,
            'created_at': firestore.SERVER_TIMESTAMP
        })

    
    user.balance += amount
    session.commit()
    new_balance = user.balance

    # Write to Firestore
    db.collection('users').document(user.uid).set({
        'balance': new_balance,
        'updated_at': firestore.SERVER_TIMESTAMP
    }, merge=True)

    session.close()

    
    return jsonify({'balance': new_balance})

@app.route('/balance/deduct', methods=['POST'])
def subtract_balance():
    print("subtract_balance")
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'error': 'No token provided'}), 401
    
    decoded_token = verify_token(token)
    if not decoded_token:
        return jsonify({'error': 'Invalid token'}), 401
    
    amount = request.json.get('amount')
    if not amount or amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400
    
    session = Session()
    user = session.query(User).filter_by(uid=decoded_token['uid']).first()
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user.balance < amount:
        return jsonify({'error': 'Insufficient balance'}), 400
    
    user.balance -= amount
    session.commit()
    new_balance = user.balance

    # Write to Firestore
    db.collection('users').document(user.uid).set({
        'balance': new_balance,
        'updated_at': firestore.SERVER_TIMESTAMP
    }, merge=True)

    session.close()
    
    return jsonify({'balance': new_balance})

# endpoints for items
@app.route('/items', methods=['GET'])
def get_items():
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'error': 'No token provided'}), 401
    
    decoded_token = verify_token(token)
    if not decoded_token:
        return jsonify({'error': 'Invalid token'}), 401
    
    session = Session()
    items = session.query(Item).filter_by(user_uid=decoded_token['uid']).all()
    
    items_list = [{
        'id': item.id,
        'item_id': item.item_id,
        'x': item.x,
        'y': item.y
    } for item in items]
    
    session.close()
    return jsonify({'items': items_list})

# endpoint to add item
@app.route('/items', methods=['POST'])
def add_item():
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'error': 'No token provided'}), 401
    
    decoded_token = verify_token(token)
    if not decoded_token:
        return jsonify({'error': 'Invalid token'}), 401
    
    data = request.json
    item_id = data.get('item_id')
    x = data.get('x')
    y = data.get('y')
    
    if item_id is None or x is None or y is None:
        return jsonify({'error': 'Missing required fields'}), 400
    
    session = Session()
    new_item = Item(
        user_uid=decoded_token['uid'],
        item_id=item_id,
        x=x,
        y=y
    )
    session.add(new_item)
    session.commit()
    
    item_data = {
        'id': new_item.id,
        'item_id': new_item.item_id,
        'x': new_item.x,
        'y': new_item.y
    }
    
    session.close()
    return jsonify(item_data)

# endpoint to update item, should not really be used
@app.route('/items/<int:item_id>', methods=['PUT'])
def update_item(item_id):
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'error': 'No token provided'}), 401
    
    decoded_token = verify_token(token)
    if not decoded_token:
        return jsonify({'error': 'Invalid token'}), 401
    
    data = request.json
    x = data.get('x')
    y = data.get('y')
    
    if x is None or y is None:
        return jsonify({'error': 'Missing required fields'}), 400
    
    session = Session()
    item = session.query(Item).filter_by(
        id=item_id,
        user_uid=decoded_token['uid']
    ).first()
    
    if not item:
        session.close()
        return jsonify({'error': 'Item not found'}), 404
    
    item.x = x
    item.y = y
    session.commit()
    
    item_data = {
        'id': item.id,
        'item_id': item.item_id,
        'x': item.x,
        'y': item.y
    }
    
    session.close()
    return jsonify(item_data)

# endpoint to delete item
@app.route('/items/<int:item_id>', methods=['DELETE'])
def delete_item(item_id):
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'error': 'No token provided'}), 401
    
    decoded_token = verify_token(token)
    if not decoded_token:
        return jsonify({'error': 'Invalid token'}), 401
    
    session = Session()
    item = session.query(Item).filter_by(
        id=item_id,
        user_uid=decoded_token['uid']
    ).first()
    
    if not item:
        session.close()
        return jsonify({'error': 'Item not found'}), 404
    
    session.delete(item)
    session.commit()
    session.close()
    
    return jsonify({'message': 'Item deleted successfully'})

@app.route('/candle/start', methods=['POST'])
def start_candle():
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'error': 'No token provided'}), 401

    decoded_token = verify_token(token)
    if not decoded_token:
        return jsonify({'error': 'Invalid token'}), 401

    start_time_str = request.json.get('start_time')  # ISO 8601 string
    if not start_time_str:
        return jsonify({'error': 'Missing start_time'}), 400

    try:
        start_time = datetime.fromisoformat(start_time_str)
    except ValueError:
        return jsonify({'error': 'Invalid start_time format'}), 400

    session = Session()
    user = session.query(User).filter_by(uid=decoded_token['uid']).first()
    if not user:
        session.close()
        return jsonify({'error': 'User not found'}), 404

    user.candle_start_time = start_time
    session.commit()
    session.close()

    return jsonify({'message': 'Candle lit', 'start_time': start_time.isoformat()})


@app.route('/candle/status', methods=['GET'])
def candle_status():
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'error': 'No token provided'}), 401

    decoded_token = verify_token(token)
    if not decoded_token:
        return jsonify({'error': 'Invalid token'}), 401

    session = Session()
    user = session.query(User).filter_by(uid=decoded_token['uid']).first()
    session.close()

    if not user:
        return jsonify({'error': 'User not found'}), 404

    is_lit = user.candle_start_time is not None
    return jsonify({'lit': is_lit})


@app.route('/candle/end', methods=['POST'])
def end_candle():
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'error': 'No token provided'}), 401

    decoded_token = verify_token(token)
    if not decoded_token:
        return jsonify({'error': 'Invalid token'}), 401

    session = Session()
    user = session.query(User).filter_by(uid=decoded_token['uid']).first()
    if not user:
        session.close()
        return jsonify({'error': 'User not found'}), 404

    user.candle_start_time = None
    session.commit()
    session.close()

    return jsonify({'message': 'Candle extinguished'})

@app.route('/candle/start_time', methods=['GET'])
def get_candle_start_time():
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'error': 'No token provided'}), 401

    decoded_token = verify_token(token)
    if not decoded_token:
        return jsonify({'error': 'Invalid token'}), 401

    session = Session()
    user = session.query(User).filter_by(uid=decoded_token['uid']).first()
    session.close()

    if not user:
        return jsonify({'error': 'User not found'}), 404

    if not user.candle_start_time:
        return jsonify({'start_time': None})

    return jsonify({'start_time': user.candle_start_time.isoformat()})

# endpoints for altar items
@app.route('/altar/items', methods=['GET'])
def get_altar_items():
    try:
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'No token provided'}), 401
        
        decoded_token = verify_token(token)
        if not decoded_token:
            return jsonify({'error': 'Invalid token'}), 401
        
        session = Session()
        items = session.query(Item).filter_by(user_uid=decoded_token['uid']).all()
        
        items_list = [{
            'id': item.item_id,
            'uniqueId': str(item.id),
            'category': item.category,
            'position': {
                'left': item.x,
                'top': item.y
            }
        } for item in items]
        
        session.close()
        return jsonify({'items': items_list})
    except Exception as e:
        print("Error in get_altar_items:", str(e))  # Debug log
        return jsonify({'error': str(e)}), 500

@app.route('/altar/items', methods=['POST'])
def save_altar_item():
    try:
        print("=== Starting save_altar_item ===")
        token = request.headers.get('Authorization')
        print("Authorization header:", token)
        
        if not token:
            return jsonify({'error': 'No token provided'}), 401
        
        decoded_token = verify_token(token)
        print("Decoded token:", decoded_token)
        
        if not decoded_token:
            return jsonify({'error': 'Invalid token'}), 401
        
        data = request.json
        print("Received data:", data)
        
        item_id = data.get('id')
        category = data.get('category')
        position = data.get('position')
        
        print("Parsed fields:", {
            'item_id': item_id,
            'category': category,
            'position': position
        })
        
        if not all([item_id, category, position, 'left' in position, 'top' in position]):
            print("Missing fields:", {
                'item_id': item_id,
                'category': category,
                'position': position
            })
            return jsonify({'error': 'Missing required fields'}), 400
        
        try:
            session = Session()
            print("Creating new item with data:", {
                'user_uid': decoded_token['uid'],
                'item_id': item_id,
                'category': category,
                'x': position['left'],
                'y': position['top']
            })
            
            new_item = Item(
                user_uid=decoded_token['uid'],
                item_id=item_id,
                category=category,
                x=position['left'],
                y=position['top']
            )
            session.add(new_item)
            session.commit()
            print("Item saved to SQLite successfully")
            
            # Also save to Firestore
            try:
                firestore_data = {
                    'item_id': item_id,
                    'category': category,
                    'position': {
                        'left': position['left'],
                        'top': position['top']
                    },
                    'created_at': firestore.SERVER_TIMESTAMP
                }
                print("Saving to Firestore:", firestore_data)
                
                db.collection('users').document(decoded_token['uid']).collection('altar_items').document(str(new_item.id)).set(firestore_data)
                print("Item saved to Firestore successfully")
            except Exception as e:
                print("Firestore error:", str(e))
                # Continue even if Firestore fails
            
            item_data = {
                'id': new_item.item_id,
                'uniqueId': str(new_item.id),
                'category': new_item.category,
                'position': {
                    'left': new_item.x,
                    'top': new_item.y
                }
            }
            
            session.close()
            print("=== save_altar_item completed successfully ===")
            return jsonify(item_data)
            
        except Exception as e:
            print("Database error:", str(e))
            if session:
                session.rollback()
                session.close()
            raise e
            
    except Exception as e:
        print("Error in save_altar_item:", str(e))
        import traceback
        print("Full traceback:", traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/altar/items/<string:unique_id>', methods=['DELETE'])
def delete_altar_item(unique_id):
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'error': 'No token provided'}), 401
    
    decoded_token = verify_token(token)
    if not decoded_token:
        return jsonify({'error': 'Invalid token'}), 401
    
    session = Session()
    item = session.query(Item).filter_by(
        id=int(unique_id),
        user_uid=decoded_token['uid']
    ).first()
    
    if not item:
        session.close()
        return jsonify({'error': 'Item not found'}), 404
    
    # Delete from Firestore
    db.collection('users').document(decoded_token['uid']).collection('altar_items').document(unique_id).delete()
    
    session.delete(item)
    session.commit()
    session.close()
    
    return jsonify({'message': 'Item deleted successfully'})

    
if __name__ == '__main__':
    # For local development
    app.run(debug=True)
else:
    # For GCP deployment
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
