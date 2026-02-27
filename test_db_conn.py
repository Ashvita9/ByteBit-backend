import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

mongo_uri = os.getenv('MONGO_URI')
print(f"Testing connection to: {mongo_uri[:30]}...")

try:
    client = MongoClient(mongo_uri)
    # The ismaster command is cheap and does not require auth.
    client.admin.command('ismaster')
    print("MongoDB Connection Successful!")
    
    db = client.get_database('codingarena_db')
    print(f"Connected to database: {db.name}")
    
    # Check collections
    collections = db.list_collection_names()
    print(f"Collections found: {collections}")
    
except Exception as e:
    print(f"MongoDB Connection Failed: {e}")
