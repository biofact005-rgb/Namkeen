import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import os, threading

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
WEB_APP_URL = os.environ.get("WEB_APP_URL") 
ADMIN_ID = 8718760365 
BIN_CHANNEL = int(os.environ.get("BIN_CHANNEL", "-1000000000000")) # 🔴 Apna Channel ID Env me dalein

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
CORS(app)

from pymongo import MongoClient
MONGO_URI = os.environ.get("MONGO_URI") 
client = MongoClient(MONGO_URI)
db = client['bseb_video_db'] 
db_collection = db['app_data']

def load_db():
    doc = db_collection.find_one({"_id": "main_data"})
    if doc and "data" in doc: return doc["data"]
    return {"users": {}, "videos": []}

def save_db(db_data):
    db_collection.update_one({"_id": "main_data"}, {"$set": {"data": db_data}}, upsert=True)

db_data = load_db()

# ==========================================
# 📝 VIDEO TXT PARSER (Title | Video | PDF | DPP)
# ==========================================
def parse_video_txt(content):
    lines = content.splitlines()
    meta = {"path": [], "mode": "video"} 
    videos = []
    
    def clean_link(url):
        if url == "#": return url
        url = url.replace("http://https://", "https://")
        url = url.replace("https://https://", "https://")
        if ":10000" in url: url = url.replace(":10000", "")
        return url.strip()
    
    for line in lines[:5]:
        if line.lower().startswith("path:"): 
            meta["path"] = [p.strip() for p in line.split(":", 1)[1].strip().split("/") if p.strip()]
            
    if not meta["path"]: return None, "❌ Header Missing!"
    
    for line in lines:
        if "|" in line and not line.upper().startswith("PATH:"):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2:
                vid_title = parts[0].strip()
                vid_url = clean_link(parts[1])
                pdf_url = clean_link(parts[2]) if len(parts) > 2 else "#"
                dpp_url = clean_link(parts[3]) if len(parts) > 3 else "#" # Naya DPP column
                videos.append({"title": vid_title, "url": vid_url, "pdf": pdf_url, "dpp": dpp_url})
                
    return meta, videos

@bot.message_handler(commands=['start'])
def start(m):
    uid = str(m.from_user.id)
    if uid not in db_data['users']:
        db_data['users'][uid] = {"name": m.from_user.first_name}
        save_db(db_data)
        
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("▶️ ENTER NAMKEEN BATCH 🍿", web_app=WebAppInfo(url=WEB_APP_URL)))
    caption = f"🚀 <b>Welcome to Namkeen Batch!</b>\n\nEkdum HD aur bina buffering ke lectures dekho!"
    bot.send_message(m.chat.id, caption, reply_markup=markup, parse_mode="HTML")

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    if str(message.from_user.id) != str(ADMIN_ID): return 
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        meta, parsed_vids = parse_video_txt(downloaded.decode('utf-8'))
        if not meta: return bot.reply_to(message, parsed_vids) 
        
        db_data['videos'] = [v for v in db_data.get('videos', []) if v.get('path') != meta['path']]
        db_data['videos'].append({"path": meta['path'], "mode": meta['mode'], "data": parsed_vids})
        save_db(db_data)
        bot.reply_to(message, f"✅ <b>Upload Success!</b>\n📂 Path: {' ➔ '.join(meta['path'])}\n🎥 Lectures: {len(parsed_vids)}", parse_mode="HTML")
    except Exception as e: bot.reply_to(message, f"❌ Error: {e}")

# ==========================================
# 🌐 API ROUTES (FLASK)
# ==========================================
@app.route('/')
def index(): return render_template('index.html') 

@app.route('/api/get_data')
def get_data():
    tree = {}
    for doc in db_data.get('videos', []):
        path = doc.get('path', [])
        if not path: continue
        curr = tree
        for p in path[:-1]:
            if p not in curr: curr[p] = {}
            curr = curr[p]
        curr[path[-1]] = {"data": doc['data'], "mode": doc.get('mode', 'video')}
    return jsonify(tree)

@app.route('/api/admin/delete', methods=['POST'])
def delete_item():
    data = request.json
    if str(data.get('uid')) != str(ADMIN_ID): return jsonify({"error": "Not Admin!"})
    target_path = data.get('path', []) + [data.get('target')]
    try:
        db_data['videos'] = [v for v in db_data.get('videos', []) if not (v.get('path', [])[:len(target_path)] == target_path)]
        save_db(db_data)
        return jsonify({"status": "deleted"})
    except Exception as e: return jsonify({"error": str(e)})

# 📥 MAGIC ROUTE: App se URL aayega, ye id nikal kar seedha chat me DM karega (protect_content ke sath)
@app.route('/api/send_to_chat', methods=['POST'])
def send_to_chat():
    data = request.json
    uid = data.get('uid')
    url = data.get('url')
    title = data.get('title')
    item_type = data.get('type') 
    
    try:
        # Stream URL se message ID nikalna (e.g. domain.com/15/video.mp4 -> ID is 15)
        msg_id = None
        for part in url.split('/'):
            if part.isdigit():
                msg_id = int(part)
                break
                
        if msg_id:
            caption = f"📚 **{title}**\n📍 Type: {item_type.upper()}\n\n*Downloaded via Namkeen Batch*"
            # copy_message forward tag hata deta hai. protect_content = screen record/forward block
            bot.copy_message(chat_id=uid, from_chat_id=BIN_CHANNEL, message_id=msg_id, protect_content=True, caption=caption, parse_mode="Markdown")
            return jsonify({"status": "success"})
        else:
            return jsonify({"error": "Link invalid hai!"})
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == "__main__":
    t = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000))))
    t.start()
    bot.infinity_polling()
