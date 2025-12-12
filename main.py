import requests
import json
import os
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- API Bilgileri ---
PLANTNET_API_KEY = os.getenv("PLANTNET_API_KEY")
PLANTNET_PROJECT = "all"
PLANTNET_URL = f"https://my-api.plantnet.org/v2/identify/{PLANTNET_PROJECT}?api-key={PLANTNET_API_KEY}"

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Admin ID'lerini buraya ekle (Telegram User ID'n)
ADMIN_IDS = os.getenv("ADMIN_IDS")  # Kendi Telegram ID'ni buraya yaz

# Veritabanı dosyaları
USERS_FILE = "users_data.json"
PLANTS_FILE = "plants_data.json"

# --- Veri Yönetimi ---
def load_data(filename):
    """JSON dosyasından veri yükler"""
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_data(filename, data):
    """JSON dosyasına veri kaydeder"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_user(user_id, username=None):
    """Yeni kullanıcı ekler veya günceller"""
    users = load_data(USERS_FILE)
    today = datetime.now().strftime("%Y-%m-%d")
    
    if str(user_id) not in users:
        users[str(user_id)] = {
            "username": username,
            "first_seen": today,
            "last_active": today,
            "search_count": 0
        }
    else:
        users[str(user_id)]["last_active"] = today
        users[str(user_id)]["search_count"] += 1
    
    save_data(USERS_FILE, users)

def add_plant_record(plant_name, user_id):
    """Tanımlanan bitki kaydı ekler"""
    plants = load_data(PLANTS_FILE)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if plant_name not in plants:
        plants[plant_name] = {
            "count": 0,
            "users": [],
            "first_seen": timestamp,
            "last_seen": timestamp
        }
    
    plants[plant_name]["count"] += 1
    plants[plant_name]["last_seen"] = timestamp
    
    if str(user_id) not in plants[plant_name]["users"]:
        plants[plant_name]["users"].append(str(user_id))
    
    save_data(PLANTS_FILE, plants)

def get_daily_users():
    """Bugün aktif olan kullanıcı sayısını döndürür"""
    users = load_data(USERS_FILE)
    today = datetime.now().strftime("%Y-%m-%d")
    return sum(1 for u in users.values() if u["last_active"] == today)

def get_total_users():
    """Toplam kullanıcı sayısını döndürür"""
    users = load_data(USERS_FILE)
    return len(users)

def is_admin(user_id):
    """Kullanıcının admin olup olmadığını kontrol eder"""
    return user_id in ADMIN_IDS

# --- PlantNet ile bitki tanımlama ---
def identify_plant(image_path):
    """Görseli PlantNet API'ye gönderir ve bitki adını döndürür"""
    try:
        files = [("images", (image_path, open(image_path, "rb"), "image/jpeg"))]
        data = {"organs": ["auto"]}
        
        response = requests.post(PLANTNET_URL, files=files, data=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("results"):
                best_match = result["results"][0]
                scientific_name = best_match.get("species", {}).get("scientificNameWithoutAuthor", "Näbelli")
                common_names = best_match.get("species", {}).get("commonNames", [])
                score = best_match.get("score", 0)
                
                return {
                    "success": True,
                    "scientific_name": scientific_name,
                    "common_names": common_names,
                    "confidence": score
                }
        return {"success": False, "error": "Bitki tapylmady"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# --- Gemini'den bitki bilgisi alma ---
def get_plant_info(plant_name):
    """Gemini API'den bitki hakkında bilgi alır"""
    try:
        headers = {
            "Content-Type": "application/json",
            "X-goog-api-key": GEMINI_API_KEY
        }
        
        prompt = f"""Sen tejribeli bir ösümlik idegçisi hökmünde hereket edýän kömekçisiň. Ulanyjy saňa '{plant_name}' ösümligi barada sorýar. Jogaby diňe Türkmen dilinde, gysga, düşnükli we amaly görnüşde ber.

Jogap şu bölümleri öz içine alsyn:

🌿 1) Ösümligiň umumy tanadylyşy
   - 2–3 sözlemde gysga maglumat
   - Ösümligiň gelip çykyşy ýa-da aýratynlygy

💧 2) Ideg boýunça maslahatlar
   - **Suw bermek:** näçe gezek, nähili usul, duýduryjy alamatlar
   - **Yşyklandyryş:** göni gün şöhlesine bolan islegi, ýagtylygyň derejesi
   - **Temperatura:** gyş/yaz aralygy, sowuga we yssya çydamlylygy
   - **Toprak:** näme görnüşde toprak, drenaj talaby
   - **Dökün:** haýsy döwürde, näçe wagtyň dowamynda, nähili dökün

🛡️ 3) Goşmaça amaly maglumatlar
   - Köp duş gelinýän meseleler we olara çalt çözgüt
   - Ösümligiň çyglylyk islegi ýa-da howa şerti
   - Haýwanlar üçin zäherliligi (eger degişli bolsa)

Jogap takmynan **150–200 söz** aralygynda bolsun. Bezeg üçin az-azdan emojiler ulan. Dostana, düşnükli üslup ulan. Artykmaç zatlar aýtma. Jogaba "salam, bolýar" ýaly sözler bilen başlama!"""

        data = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        
        response = requests.post(GEMINI_API_URL, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            text_output = result["candidates"][0]["content"]["parts"][0]["text"]
            return {"success": True, "info": text_output}
        return {"success": False, "error": "Maglumat alnyp bilinmedi"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# --- Telegram Bot Komutları ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot başlatma komutu"""
    user_id = update.effective_user.id
    username = update.effective_user.username
    add_user(user_id, username)
    
    welcome_message = """🌿 Salam! Men ösümlikleriňizi tanamak we ideg etmek boýunça maslahat berýän bot.

📸 Ösümligiňiziň suratyny iberseňiz, men ony tanaýaryn we ideg etmek boýunça maslahat berýärin!

Size haýsy ösümlik barada maglumat gerek?"""
    
    await update.message.reply_text(welcome_message)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kullanıcıdan gelen fotoğrafı işler"""
    user_id = update.effective_user.id
    username = update.effective_user.username
    add_user(user_id, username)
    
    processing_msg = await update.message.reply_text(
        "📸 Suratyňyz alyndy!\n⏳ Ösümligi gözleýärin, 1-2 minut garaşyň..."
    )
    
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_path = f"temp_{update.message.chat_id}.jpg"
        await photo_file.download_to_drive(photo_path)
        
        await processing_msg.edit_text(
            "🔍 Ösümlik tanalmaga başlandy...\n⏳ Birazajyk wagt garaşyň..."
        )
        
        plant_result = identify_plant(photo_path)
        
        if not plant_result["success"]:
            await processing_msg.edit_text(
                f"❌ Ösümlik tapylmady. Täzeden synanyşyň.\n\nÝalňyşlyk: {plant_result.get('error', 'Näbelli')}"
            )
            os.remove(photo_path)
            return
        
        scientific_name = plant_result["scientific_name"]
        confidence = plant_result["confidence"] * 100
        
        # Bitki kaydını ekle
        add_plant_record(scientific_name, user_id)
        
        await processing_msg.edit_text(
            f"✅ Ösümlik tapyldy: {scientific_name}\n\n🤖 Häzir bu ösümlik barada maglumat gözleýärin..."
        )
        
        info_result = get_plant_info(scientific_name)
        
        if info_result["success"]:
            response = f"""🌱 <b>Ösümligiňiz Tapyldy!</b>

🔬 <b>Ylmy ady:</b> {scientific_name}
📊 <b>Dogrulyk:</b> {confidence:.1f}%

━━━━━━━━━━━━━━━━━━

{info_result['info']}

━━━━━━━━━━━━━━━━━━

💚 Ösümligiňize gowy ideg ediň!"""
        else:
            response = f"""🌱 <b>Ösümlik Tapyldy!</b>

🔬 <b>Ylmy ady:</b> {scientific_name}
📊 <b>Dogrulyk:</b> {confidence:.1f}%

❌ Gynansagam, bu ösümlik barada giňişleýin maglumat tapyp bilmedik. Başga surat bilen synanyşyp bilersiňiz."""
        
        await processing_msg.edit_text(response, parse_mode='HTML')
        os.remove(photo_path)
        
    except Exception as e:
        await processing_msg.edit_text(
            f"❌ Ýalňyşlyk ýüze çykdy: {str(e)}\n\nTäzeden synanyşyň ýa-da başga surat iberiň."
        )
        if os.path.exists(photo_path):
            os.remove(photo_path)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yardım komutu"""
    help_text = """🌿 <b>Bot Ulanyş Gollanmasy</b>

Bu bot siziň ösümligiňizi tanamaga we ideg etmek boýunça maslahat bermäge kömek eder.

<b>Nädip ulanmaly:</b>
1️⃣ Ösümligiňiziň aýdyň suratyny düşüriň
2️⃣ Suraty şu bota iberiň
3️⃣ Bot ösümligiňizi tanaýar we maglumat berýär

<b>Maslahatlar:</b>
• Suratyň hili gowy bolsun
• Ösümligiňiziň ýapraklaryny ýa-da güllerini görkeziň
• Yşyk ýeterlik bolsun

📸 Häzir suratyňyzy iberip bilersiňiz!"""
    
    await update.message.reply_text(help_text, parse_mode='HTML')

# --- ADMIN KOMUTLARI ---
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: İstatistikleri gösterir"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Bu diňe adminler üçin!")
        return
    
    total_users = get_total_users()
    daily_users = get_daily_users()
    plants = load_data(PLANTS_FILE)
    total_plants = len(plants)
    total_searches = sum(p["count"] for p in plants.values())
    
    stats_text = f"""📊 <b>BOT STATISTIKA</b>

👥 <b>Ulanyjylar:</b>
   • Jemi: {total_users} ulanyjy
   • Bugünkiler: {daily_users} ulanyjy

🌿 <b>Ösümlikler:</b>
   • Tapylan jemi ösümlik: {total_plants}
   • Jemi gözlenen: {total_searches}

📅 <b>Çislo:</b> {datetime.now().strftime("%d.%m.%Y %H:%M")}"""
    
    await update.message.reply_text(stats_text, parse_mode='HTML')

async def admin_plants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: Tüm tanımlanan bitkileri listeler"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Bu diňe adminler üçin!")
        return
    
    plants = load_data(PLANTS_FILE)
    
    if not plants:
        await update.message.reply_text("🌿 Heniz hiç hili ösümlik tanalmandyr.")
        return
    
    # En çok aranan 20 bitki
    sorted_plants = sorted(plants.items(), key=lambda x: x[1]["count"], reverse=True)[:20]
    
    plants_text = "🌿 <b>Iň köp gözlenen ösümlikler (Top 20)</b>\n\n"
    
    for i, (name, data) in enumerate(sorted_plants, 1):
        plants_text += f"{i}. <b>{name}</b>\n"
        plants_text += f"   📊 {data['count']} gezek gözlendi\n"
        plants_text += f"   👥 {len(data['users'])} sany ulanyjy\n\n"
    
    await update.message.reply_text(plants_text, parse_mode='HTML')

async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: Toplu mesaj gönderme başlatır"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Bu diňe adminler üçin!")
        return
    
    await update.message.reply_text(
        "📢 <b>TOPLU MESAJ GÖNDERME</b>\n\n"
        "Ugradylmaly sms-y ýazyň.\n"
        "Sms hemme ulanyjylara ugradylar.\n\n"
        "Otkaz etmek üçin /cancel ýazyň.",
        parse_mode='HTML'
    )
    
    context.user_data['broadcast_mode'] = True

async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: İşlemi iptal eder"""
    if not is_admin(update.effective_user.id):
        return
    
    context.user_data['broadcast_mode'] = False
    await update.message.reply_text("❌ Otkaz edildi.")

async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: Broadcast mesajını işler"""
    if not is_admin(update.effective_user.id):
        return
    
    if not context.user_data.get('broadcast_mode'):
        return
    
    message_text = update.message.text
    users = load_data(USERS_FILE)
    
    status_msg = await update.message.reply_text(
        f"📤 SMS ugradylýar...\n0/{len(users)} tamamlandy."
    )
    
    success = 0
    failed = 0
    
    for i, user_id in enumerate(users.keys(), 1):
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text=f"📢 <b>Diňläň:</b>\n\n{message_text}",
                parse_mode='HTML'
            )
            success += 1
        except Exception as e:
            failed += 1
            print(f"Ulanyja sms ugradylmady {user_id}: {e}")
        
        # Her 10 kullanıcıda bir durum güncelle
        if i % 10 == 0:
            await status_msg.edit_text(
                f"📤 SMS ugradylýar...\n{i}/{len(users)} tamamlandy"
            )
    
    context.user_data['broadcast_mode'] = False
    
    await status_msg.edit_text(
        f"✅ <b>SMS ugradylma tamamlandy!</b>\n\n"
        f"✅ Üstünlikli: {success}\n"
        f"❌ Üstünliksiz: {failed}\n"
        f"📊 Jemi: {len(users)}",
        parse_mode='HTML'
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Metin mesajlarını işler"""
    # Broadcast modunda admin mesajını işle
    if is_admin(update.effective_user.id) and context.user_data.get('broadcast_mode'):
        await handle_broadcast_message(update, context)
        return
    
    # Normal kullanıcılar için yönlendirme
    await update.message.reply_text(
        "🌿 Ösümlik tanatmak üçin surat ugradyň!\n\n"
        "Kömek üçin /help komandany ulanyň."
    )

async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: Admin komutlarını gösterir"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Bu diňe adminler üçin!")
        return
    
    admin_help_text = """🔐 <b>ADMİN KOMANDALAR</b>

/stats - Bot statistika
/plants - Tanalan ösümlikler
/broadcast - SMS ugratmak
/cancel - Broadcast otkaz etmek
/adminhelp - Şu help i görmek"""
    
    await update.message.reply_text(admin_help_text, parse_mode='HTML')

# --- Bot'u başlat ---
def main():
    """Botu başlatır"""
    print("🤖 Bot başlaýar...")
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Normal komutlar
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # Admin komutları
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("plants", admin_plants))
    application.add_handler(CommandHandler("broadcast", admin_broadcast_start))
    application.add_handler(CommandHandler("cancel", admin_cancel))
    application.add_handler(CommandHandler("adminhelp", admin_help))
    
    # Metin mesajları handler'ı (en sonda olmalı)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("✅ Bot işläp başlady!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
