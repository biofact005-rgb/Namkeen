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

import re

admin_states = {} # 🧠 Bot ka dimag jo path aur replies yaad rakhega

# 1️⃣ PATH SET KARNE WALA COMMAND
@bot.message_handler(commands=['setpath'])
def set_path(m):
    if str(m.from_user.id) != str(ADMIN_ID): return
    path_str = m.text.replace('/setpath', '').strip()
    if not path_str:
        return bot.reply_to(m, "⚠️ Format: `/setpath Folder 1/Folder 2`", parse_mode="Markdown")
    
    path_list = [p.strip() for p in path_str.split('/') if p.strip()]
    admin_states.setdefault(m.from_user.id, {})['path'] = path_list
    bot.reply_to(m, f"📂 **Path Ready:** `{' ➔ '.join(path_list)}`\n\n🔥 Ab ek sath jitni marzi videos forward maaro!", parse_mode="Markdown")

# 2️⃣ NAAM BADALNE WALA COMMAND
@bot.message_handler(commands=['rename'])
def rename_vid(m):
    if str(m.from_user.id) != str(ADMIN_ID): return
    if not m.reply_to_message: return bot.reply_to(m, "⚠️ Naye naam ke liye pehle video ke 'Saved' message par reply karo!")
    
    new_title = m.text.replace('/rename', '').strip()
    if not new_title: return bot.reply_to(m, "⚠️ Naam toh likho! `/rename L1: New Title`")
    
    reply_map = admin_states.get(m.from_user.id, {}).get('reply_map', {})
    target_msg_id = m.reply_to_message.message_id
    
    if target_msg_id in reply_map:
        vid_info = reply_map[target_msg_id]
        for v in db_data.get('videos', []):
            if v.get('path') == vid_info['path']:
                for vid in v['data']:
                    if vid['url'] == vid_info['vid_url']:
                        vid['title'] = new_title
                        save_db(db_data)
                        return bot.reply_to(m, f"✅ **Naam badal gaya:**\n`{new_title}`", parse_mode="Markdown")
        bot.reply_to(m, "❌ Video database me nahi mili.")

# 3️⃣ ASLI JAADU (FILE, VIDEO & TXT HANDLER)
@bot.message_handler(content_types=['video', 'document', 'audio'])
def handle_media(m):
    if str(m.from_user.id) != str(ADMIN_ID): return
    
    # 📝 FALLBACK: Agar TXT File upload ki toh purana system chalega
    if m.content_type == 'document' and m.document.file_name.endswith('.txt'):
        try:
            file_info = bot.get_file(m.document.file_id)
            downloaded = bot.download_file(file_info.file_path)
            meta, parsed_vids = parse_video_txt(downloaded.decode('utf-8'))
            if not meta: return bot.reply_to(m, parsed_vids) 
            
            db_data['videos'] = [v for v in db_data.get('videos', []) if v.get('path') != meta['path']]
            db_data['videos'].append({"path": meta['path'], "mode": meta['mode'], "data": parsed_vids})
            save_db(db_data)
            return bot.reply_to(m, f"✅ **TXT Upload Success!**\n📂 Path: {' ➔ '.join(meta['path'])}\n🎥 Lectures: {len(parsed_vids)}", parse_mode="Markdown")
        except Exception as e: return bot.reply_to(m, f"❌ TXT Error: {e}")

    # 📄 IF REPLYING WITH PDF (Notes ya DPP add karna)
    reply_map = admin_states.get(m.from_user.id, {}).get('reply_map', {})
    if m.reply_to_message and m.reply_to_message.message_id in reply_map:
        vid_info = reply_map[m.reply_to_message.message_id]
        copied_pdf = bot.copy_message(BIN_CHANNEL, m.chat.id, m.message_id)
        pdf_url = f"https://bot.local/{copied_pdf.message_id}/file.pdf"
        
        is_dpp = m.caption and '/dpp' in m.caption.lower()
        
        for v in db_data.get('videos', []):
            if v.get('path') == vid_info['path']:
                for vid in v['data']:
                    if vid['url'] == vid_info['vid_url']:
                        if is_dpp:
                            vid['dpp'] = pdf_url
                            msg_type = "📝 DPP"
                        else:
                            vid['pdf'] = pdf_url
                            msg_type = "📄 Class Notes"
                        save_db(db_data)
                        return bot.reply_to(m, f"✅ **{msg_type} Attached Successfully!**", parse_mode="Markdown")

    # 🎥 IF UPLOADING/FORWARDING NEW VIDEO
    target_path = admin_states.get(m.from_user.id, {}).get('path')
    if not target_path:
        return bot.reply_to(m, "❌ **Pehle path set karo!**\nLikkho: `/setpath Folder Name/Subject`", parse_mode="Markdown")
        
    try:
        # Seedha Bin me Copy
        copied_vid = bot.copy_message(BIN_CHANNEL, m.chat.id, m.message_id)
        vid_url = f"https://bot.local/{copied_vid.message_id}/video.mp4"
        
        # Smart Caption Cleaner 🧹
        raw_caption = m.caption if m.caption else (m.document.file_name if m.content_type == 'document' else "Untitled Video")
        lines = [line.strip() for line in raw_caption.split('\n') if line.strip()]
        title = lines[0] if lines else "Untitled Video"
        
        # Kachra saaf (remove @usernames and links)
        title = re.sub(r'@\w+', '', title)
        title = re.sub(r'http\S+|www.\S+|t\.me/\S+', '', title)
        title = title.replace('.mp4', '').replace('.mkv', '').strip()
        if not title: title = "Untitled Lecture"
        
        # DB me save karo
        doc_found = False
        if 'videos' not in db_data: db_data['videos'] = []
        
        for v in db_data['videos']:
            if v.get('path') == target_path:
                v.setdefault('data', []).append({"title": title, "url": vid_url, "pdf": "#", "dpp": "#"})
                doc_found = True
                break
        
        if not doc_found:
            db_data['videos'].append({"path": target_path, "mode": "video", "data": [{"title": title, "url": vid_url, "pdf": "#", "dpp": "#"}]})
            
        save_db(db_data)
        
        # Reply with Instructions (Isi reply ke zariye Notes judenge)
        reply_msg = bot.reply_to(m, f"✅ **Saved:** `{title}`\n\n_1. Notes ke liye is msg par PDF reply karo.\n2. DPP ke liye is msg par PDF + caption me /dpp likh kar reply karo.\n3. Naam badalne ke liye reply me /rename Naya Naam likho._", parse_mode="Markdown")
        
        # Agli baar reply pe pehchanne ke liye memory me save
        admin_states.setdefault(m.from_user.id, {})['reply_map'] = admin_states.get(m.from_user.id, {}).get('reply_map', {})
        admin_states[m.from_user.id]['reply_map'][reply_msg.message_id] = {"path": target_path, "vid_url": vid_url}
        
    except Exception as e:
        bot.reply_to(m, f"❌ Error adding video: {e}")

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
