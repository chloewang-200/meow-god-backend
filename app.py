from flask import Flask, request, jsonify
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, auth
from sqlalchemy import create_engine, Column, String, Float, Integer, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Initialize Firebase Admin
cred = credentials.Certificate({
    "type": "service_account",
    "project_id": "meow-god",
    "private_key_id": os.getenv('FIREBASE_PRIVATE_KEY_ID'),
    "private_key": os.getenv('FIREBASE_PRIVATE_KEY').replace('\\n', '\n'),
    "client_email": os.getenv('FIREBASE_CLIENT_EMAIL'),
    "client_id": os.getenv('FIREBASE_CLIENT_ID'),
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": os.getenv('FIREBASE_CLIENT_CERT_URL')
})
firebase_admin.initialize_app(cred)

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
    x = Column(Integer)  # x position
    y = Column(Integer)  # y position

# User model
class User(Base):
    __tablename__ = 'users'
    
    uid = Column(String, primary_key=True)
    balance = Column(Float, default=0.0)

# Create tables
Base.metadata.create_all(engine)

def verify_token(token):
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        return None

@app.route('/balance', methods=['GET'])
def get_balance():
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'error': 'No token provided'}), 401
    
    decoded_token = verify_token(token)
    if not decoded_token:
        return jsonify({'error': 'Invalid token'}), 401
    
    session = Session()
    user = session.query(User).filter_by(uid=decoded_token['uid']).first()
    
    if not user:
        user = User(uid=decoded_token['uid'], balance=0.0)
        session.add(user)
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
    
    user.balance += amount
    session.commit()
    new_balance = user.balance
    session.close()
    
    return jsonify({'balance': new_balance})

@app.route('/balance/subtract', methods=['POST'])
def subtract_balance():
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

if __name__ == '__main__':
    app.run(debug=True)
