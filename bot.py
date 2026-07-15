import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import os, threading, json
from datetime import datetime

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://your-app-url.onrender.com") 
ADMIN_ID = 8718760365 # Apni ID

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
CORS(app)

# ==========================================
# 🗄️ DATABASE (MongoDB)
# ==========================================
from pymongo import MongoClient
MONGO_URI = os.environ.get("MONGO_URI") 
client = MongoClient(MONGO_URI)
db = client['bseb_video_db'] # Database name changed
db_collection = db['app_data']

def load_db():
    doc = db_collection.find_one({"_id": "main_data"})
    if doc and "data" in doc: return doc["data"]
    return {"users": {}, "videos": []}

def save_db(db_data):
    db_collection.update_one({"_id": "main_data"}, {"$set": {"data": db_data}}, upsert=True)

db_data = load_db()

# ==========================================
# 📝 VIDEO TXT PARSER (For Admin Upload)
# ==========================================
def parse_video_txt(content):
    lines = content.splitlines()
    meta = {"path": [], "mode": "video"} 
    videos = []
    
    for line in lines[:5]:
        lower = line.lower()
        if lower.startswith("path:"): 
            meta["path"] = [p.strip() for p in line.split(":", 1)[1].strip().split("/") if p.strip()]
            
    if not meta["path"]: return None, "❌ Header Missing! Example -> Path: Namkeen Batch / Physics"
    
    for line in lines:
        if "|" in line and not line.upper().startswith("PATH:"):
            parts = [p.strip() for p in line.split("|")]
            # Format: Lecture Title | Video Link | PDF Link (Optional)
            if len(parts) >= 2:
                vid_title = parts[0]
                vid_url = parts[1]
                pdf_url = parts[2] if len(parts) > 2 else "#"
                videos.append({"title": vid_title, "url": vid_url, "pdf": pdf_url})
                
    return meta, videos

# ==========================================
# 🤖 BOT HANDLERS 
# ==========================================
@bot.message_handler(commands=['start'])
def start(m):
    uid = str(m.from_user.id)
    first_name = m.from_user.first_name
    
    # User Registration
    if uid not in db_data['users']:
        db_data['users'][uid] = {"name": first_name, "joined": str(datetime.now())}
        save_db(db_data)
        
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("▶️ ENTER NAMKEEN BATCH 🍿", web_app=WebAppInfo(url=WEB_APP_URL)))
    
    caption = f"🚀 <b>Welcome to Namkeen Batch!</b>\n\n👤 <b>Student:</b> {first_name}\n🆔 <b>ID:</b> <code>{uid}</code>\n\nEkdum HD aur bina buffering ke lectures dekho, saath hi speed control ka maza lo! Click below to start."
    bot.send_message(m.chat.id, caption, reply_markup=markup, parse_mode="HTML")

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    if str(message.from_user.id) != str(ADMIN_ID): return 
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        content = downloaded.decode('utf-8')
        
        meta, parsed_vids = parse_video_txt(content)
        if not meta: return bot.reply_to(message, parsed_vids) 
        
        # Remove old data of same path and add new
        db_data['videos'] = [v for v in db_data.get('videos', []) if v.get('path') != meta['path']]
        db_data['videos'].append({"path": meta['path'], "mode": meta['mode'], "data": parsed_vids})
        save_db(db_data)
        
        bot.reply_to(message, f"✅ <b>Upload Success!</b>\n📂 Path: {' ➔ '.join(meta['path'])}\n🎥 Lectures: {len(parsed_vids)}", parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

# ==========================================
# 🌐 API ROUTES (FLASK)
# ==========================================
@app.route('/')
def index(): 
    return render_template('index.html') 

@app.route('/api/get_data')
def get_data():
    tree = {}
    for doc in db_data.get('videos', []):
        path = doc.get('path', [])
        if not path: continue
        current_level = tree
        for p in path[:-1]:
            if p not in current_level: current_level[p] = {}
            current_level = current_level[p]
        current_level[path[-1]] = {"data": doc['data'], "mode": doc.get('mode', 'video')}
    return jsonify(tree)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    t = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=port))
    t.start()
    bot.infinity_polling()
