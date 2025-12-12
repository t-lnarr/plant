import requests
import json
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- API Bilgileri ---
PLANTNET_API_KEY = os.getenv("PLANTNET_API_KEY")
PLANTNET_PROJECT = "all"
PLANTNET_URL = f"https://my-api.plantnet.org/v2/identify/{PLANTNET_PROJECT}?api-key={PLANTNET_API_KEY}"

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # BotFather'dan alacağın token


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
                # En yüksek skorlu sonucu al
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
               - Ösümligiň gelip çykşy ýa-da aýratynlygy

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

            Jogap takmynan **150–200 söz** aralygynda bolsun. Bezeg üçin az-azdan emojiler ulan. Dostana, düşnükli üslup ulan. Artykmaç zatlar aýtma. Jogaba "salam, bolýar" ýaly sözler bilen başlama!
            """

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
    welcome_message = """🌿 Salam! Men ösümlikleriňizi tanamak we ideg etmek boýunça maslahat berýän bot.

📸 Ösümligiňiziň suratyny iberseňiz, men ony tanaýaryn we ideg etmek boýunça maslahat berýärin!

Size haýsy ösümlik barada maglumat gerek?"""

    await update.message.reply_text(welcome_message)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kullanıcıdan gelen fotoğrafı işler"""

    # İlk mesaj
    processing_msg = await update.message.reply_text(
        "📸 Suratyňyz alyndy!\n⏳ Ösümligi gözleýärin, 1-2 minut garaşyň..."
    )

    try:
        # Fotoğrafı indir
        photo_file = await update.message.photo[-1].get_file()
        photo_path = f"temp_{update.message.chat_id}.jpg"
        await photo_file.download_to_drive(photo_path)

        # PlantNet ile tanımlama
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

        # Gemini'den bilgi al
        await processing_msg.edit_text(
            f"✅ Ösümlik tapyldy: {scientific_name}\n\n🤖 Häzir bu ösümlik barada maglumat gözleýärin..."
        )

        info_result = get_plant_info(scientific_name)

        # Sonuçları hazırla
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

        # Geçici dosyayı sil
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


# --- Bot'u başlat ---
def main():
    """Botu başlatır"""
    print("🤖 Bot başlaýar...")

    # Application oluştur
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Komutları ekle
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Botu çalıştır
    print("✅ Bot işläp başlady!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
