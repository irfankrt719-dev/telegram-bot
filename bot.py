"""
Telegram Sipariş Botu - Otomatik Konum + Bot Üzerinden Konum Ekleme
====================================================================
Kurulum:  pip install python-telegram-bot --upgrade
Çalıştır: python bot.py
"""

import logging, json, os, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters, ConversationHandler
)

# ─── AYARLAR ────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID  = int(os.environ.get("ADMIN_ID", "0"))

BANKA_BILGILERI = """
🏦 *Ödeme Bilgileri*

Banka: Ziraat Bankası
Hesap Adı: Şirket Adı
IBAN: TR00 0000 0000 0000 0000 0000 00

💡 Açıklama kısmına *sipariş numaranızı* yazmayı unutmayın!
"""

URUNLER = {
    "urun_1": {"ad": "Ürün 1", "fiyat": 50.00},
    "urun_2": {"ad": "Ürün 2", "fiyat": 75.00},
    "urun_3": {"ad": "Ürün 3", "fiyat": 100.00},
    "urun_4": {"ad": "Ürün 4", "fiyat": 120.00},
    "urun_5": {"ad": "Ürün 5", "fiyat": 90.00},
}

BOLGELER = {
    "marmara":    "Marmara",
    "ege":        "Ege",
    "akdeniz":    "Akdeniz",
    "ic_anadolu": "İç Anadolu",
    "karadeniz":  "Karadeniz",
    "dogu":       "Doğu Anadolu",
    "guneydogu":  "Güneydoğu Anadolu",
}

URUN_SEC, BOLGE_SEC, ODEME = range(3)

# ─── DOSYA İŞLEMLERİ ────────────────────────────────────────────────────────
SIPARISLER_DOSYA = "siparisler.json"
KONUMLAR_DOSYA   = "konumlar.json"

def yukle(dosya, varsayilan={}):
    if os.path.exists(dosya):
        try:
            with open(dosya, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return varsayilan
    return varsayilan

def kaydet(dosya, data):
    with open(dosya, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

aktif_siparisler = yukle(SIPARISLER_DOSYA)
konumlar         = yukle(KONUMLAR_DOSYA, {b: [] for b in BOLGELER.values()})

# Admin konum ekleme akışı: { admin_id: { "adim": "foto"|"konum", "bolge", "foto_id" } }
konum_ekleme = {}

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── KONUM YARDIMCIları ─────────────────────────────────────────────────────
def bolge_icin_konum_sec(bolge_adi):
    for konum in konumlar.get(bolge_adi, []):
        if not konum.get("kullanildi") and konum.get("foto_id"):
            return konum
    return None

def konumu_kullanildi_isaretle(bolge_adi, konum_id):
    for konum in konumlar.get(bolge_adi, []):
        if konum["id"] == konum_id:
            konum["kullanildi"] = True
            break
    kaydet(KONUMLAR_DOSYA, konumlar)

def bolge_konum_sayisi(bolge_adi):
    return sum(1 for k in konumlar.get(bolge_adi, [])
               if not k.get("kullanildi") and k.get("foto_id"))

def siparis_no_olustur(user_id):
    return f"SP{user_id % 10000:04d}{int(time.time()) % 10000:04d}"

# ─── MÜŞTERİ AKIŞI ──────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    keyboard = [
        [InlineKeyboardButton(f"🍬 {v['ad']}  –  ₺{v['fiyat']:.2f}", callback_data=k)]
        for k, v in URUNLER.items()
    ]
    keyboard.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])
    await update.message.reply_text(
        f"👋 Merhaba *{update.effective_user.first_name}*!\n\nLütfen bir ürün seçin:",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return URUN_SEC

async def urun_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "iptal":
        await query.edit_message_text("❌ İptal edildi. /start ile yeniden başlayın.")
        return ConversationHandler.END
    urun = URUNLER.get(query.data)
    if not urun:
        await query.edit_message_text("⚠️ Geçersiz seçim.")
        return ConversationHandler.END
    context.user_data.update({"urun_kodu": query.data, "urun_ad": urun["ad"], "urun_fiyat": urun["fiyat"]})
    keyboard = [[InlineKeyboardButton(f"📌 {ad}", callback_data=kod)] for kod, ad in BOLGELER.items()]
    keyboard += [[InlineKeyboardButton("⬅️ Geri", callback_data="geri_urun")],
                 [InlineKeyboardButton("❌ İptal", callback_data="iptal")]]
    await query.edit_message_text(
        f"✅ *{urun['ad']}*  –  ₺{urun['fiyat']:.2f}\n\n📍 Bölgenizi seçin:",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return BOLGE_SEC

async def bolge_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "iptal":
        await query.edit_message_text("❌ İptal edildi.")
        return ConversationHandler.END
    if query.data == "geri_urun":
        keyboard = [[InlineKeyboardButton(f"🍬 {v['ad']}  –  ₺{v['fiyat']:.2f}", callback_data=k)]
                    for k, v in URUNLER.items()]
        keyboard.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])
        await query.edit_message_text("Lütfen bir ürün seçin:", parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup(keyboard))
        return URUN_SEC
    bolge_ad = BOLGELER.get(query.data)
    if not bolge_ad:
        await query.edit_message_text("⚠️ Geçersiz bölge.")
        return ConversationHandler.END
    siparis_no = siparis_no_olustur(update.effective_user.id)
    context.user_data.update({"bolge": bolge_ad, "siparis_no": siparis_no})
    ozet = (
        f"📋 *Sipariş Özeti*\n─────────────────\n"
        f"🔖 `{siparis_no}`\n"
        f"🍬 {context.user_data['urun_ad']}\n"
        f"📍 {bolge_ad}\n"
        f"💰 ₺{context.user_data['urun_fiyat']:.2f}\n"
        f"─────────────────\n\n{BANKA_BILGILERI}\n\n"
        "✅ Ödemeyi yaptıktan sonra *dekont fotoğrafını* gönderin."
    )
    keyboard = [
        [InlineKeyboardButton("✅ Siparişi Onayla", callback_data="onayla")],
        [InlineKeyboardButton("⬅️ Geri", callback_data="geri_bolge")],
        [InlineKeyboardButton("❌ İptal", callback_data="iptal")],
    ]
    await query.edit_message_text(ozet, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return ODEME

async def odeme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "iptal":
        await query.edit_message_text("❌ İptal edildi.")
        return ConversationHandler.END
    if query.data == "geri_bolge":
        keyboard = [[InlineKeyboardButton(f"📌 {ad}", callback_data=kod)] for kod, ad in BOLGELER.items()]
        keyboard.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])
        await query.edit_message_text("📍 Bölgenizi seçin:", parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup(keyboard))
        return BOLGE_SEC
    if query.data == "onayla":
        siparis_no = context.user_data.get("siparis_no", "?")
        aktif_siparisler[siparis_no] = {
            "user_id": update.effective_user.id,
            "urun":    context.user_data.get("urun_ad"),
            "bolge":   context.user_data.get("bolge"),
            "fiyat":   context.user_data.get("urun_fiyat"),
            "durum":   "beklemede"
        }
        kaydet(SIPARISLER_DOSYA, aktif_siparisler)
        await query.edit_message_text(
            f"🎉 Siparişiniz alındı!\n\nSipariş No: `{siparis_no}`\n\n"
            f"Havale/EFT'yi gerçekleştirip dekontu gönderin.\n\nTeşekkürler! 🙏",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

# ─── DEKONT GELDİĞİNDE ──────────────────────────────────────────────────────
async def foto_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Admin fotoğraf gönderiyorsa → konum ekleme akışı mı?
    if user_id == ADMIN_ID:
        if user_id in konum_ekleme and konum_ekleme[user_id]["adim"] == "foto":
            # Fotoğrafı kaydet, konum bekle
            konum_ekleme[user_id]["foto_id"] = update.message.photo[-1].file_id
            konum_ekleme[user_id]["adim"]    = "konum"
            bolge = konum_ekleme[user_id]["bolge"]
            await update.message.reply_text(
                f"✅ Fotoğraf kaydedildi!\n\n"
                f"Şimdi *{bolge}* için 📍 *konumu* gönder\n"
                f"_(Telegram'da konumunu paylaş veya haritadan pin bırak)_",
                parse_mode="Markdown"
            )
        else:
            # Konum ekleme akışı yoksa file_id göster
            foto_id = update.message.photo[-1].file_id
            await update.message.reply_text(
                f"📋 *Fotoğraf ID:*\n`{foto_id}`",
                parse_mode="Markdown"
            )
        return

    # Müşteri dekont gönderiyor
    siparis_no = context.user_data.get("siparis_no")
    if not siparis_no:
        for no, s in aktif_siparisler.items():
            if str(s["user_id"]) == str(user_id) and s["durum"] == "beklemede":
                siparis_no = no
                break

    if not siparis_no:
        await update.message.reply_text("⚠️ Aktif siparişiniz yok. /start ile başlayın.")
        return

    siparis  = aktif_siparisler.get(siparis_no, {})
    keyboard = [[InlineKeyboardButton(f"✅ Onayla – {siparis_no}",
                                      callback_data=f"admin_onayla:{siparis_no}")]]

    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=update.message.photo[-1].file_id,
        caption=(
            f"💰 *Yeni Dekont!*\n\n"
            f"🔖 `{siparis_no}`\n"
            f"🍬 {siparis.get('urun','?')} | 📍 {siparis.get('bolge','?')} | ₺{siparis.get('fiyat','?')}\n\n"
            f"👇 Onaylamak için butona bas:"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text(
        f"✅ Dekontunuz alındı! Sipariş No: `{siparis_no}`\nEn kısa sürede onay gönderilecektir. 🙏",
        parse_mode="Markdown"
    )

# ─── KONUM GELDİĞİNDE ───────────────────────────────────────────────────────
async def konum_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return

    # Konum ekleme akışındaysa → konumu kaydet
    if user_id in konum_ekleme and konum_ekleme[user_id]["adim"] == "konum":
        akis    = konum_ekleme[user_id]
        bolge   = akis["bolge"]
        foto_id = akis["foto_id"]
        lat     = update.message.location.latitude
        lon     = update.message.location.longitude

        # Yeni konum oluştur
        konum_id = f"{bolge.lower().replace(' ', '_').replace('ç','c').replace('ş','s').replace('ğ','g').replace('ü','u').replace('ö','o').replace('ı','i')}_{int(time.time())}"
        yeni_konum = {
            "id":        konum_id,
            "lat":       lat,
            "lon":       lon,
            "foto_id":   foto_id,
            "kullanildi": False
        }

        if bolge not in konumlar:
            konumlar[bolge] = []
        konumlar[bolge].append(yeni_konum)
        kaydet(KONUMLAR_DOSYA, konumlar)

        del konum_ekleme[user_id]

        kalan = bolge_konum_sayisi(bolge)
        await update.message.reply_text(
            f"✅ *{bolge}* bölgesine yeni konum eklendi!\n\n"
            f"📍 Koordinat: `{lat:.4f}, {lon:.4f}`\n"
            f"🗂 Bölgede toplam kullanılabilir konum: *{kalan}*\n\n"
            f"Başka konum eklemek için `/konum_ekle {bolge}` yaz.",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text("Konum alındı ama aktif işlem yok.")

# ─── ADMİN: /konum_ekle ─────────────────────────────────────────────────────
async def konum_ekle_baslat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    # Bölge listesi buton olarak göster
    if not context.args:
        keyboard = [
            [InlineKeyboardButton(f"📌 {ad}", callback_data=f"konum_ekle_bolge:{ad}")]
            for ad in BOLGELER.values()
        ]
        await update.message.reply_text(
            "Hangi bölgeye konum eklemek istiyorsun?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    bolge = " ".join(context.args)
    await konum_ekle_baslat_bolge(update, context, bolge)

async def konum_ekle_bolge_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Yetkisiz!", show_alert=True)
        return
    await query.answer()
    bolge = query.data.split(":")[1]
    await konum_ekle_baslat_bolge(query, context, bolge)

async def konum_ekle_baslat_bolge(update_or_query, context, bolge):
    admin_id = ADMIN_ID
    konum_ekleme[admin_id] = {"adim": "foto", "bolge": bolge, "foto_id": None}

    mesaj = (
        f"📍 *{bolge}* bölgesine yeni konum ekleniyor\n\n"
        f"*Adım 1:* Bu konuma ait 📸 *fotoğrafı* gönder"
    )

    if hasattr(update_or_query, 'edit_message_text'):
        await update_or_query.edit_message_text(mesaj, parse_mode="Markdown")
    else:
        await update_or_query.message.reply_text(mesaj, parse_mode="Markdown")

# ─── ADMİN BUTON: Sipariş Onayla ────────────────────────────────────────────
async def admin_buton_onayla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Yetkisiz!", show_alert=True)
        return

    await query.answer()
    siparis_no = query.data.split(":")[1]
    siparis    = aktif_siparisler.get(siparis_no)

    if not siparis:
        await query.edit_message_caption(f"⚠️ `{siparis_no}` bulunamadı.", parse_mode="Markdown")
        return

    if siparis["durum"] in ("isleniyor", "tamamlandi"):
        await query.answer(f"Bu sipariş zaten {siparis['durum']}!", show_alert=True)
        return

    bolge = siparis["bolge"]
    konum = bolge_icin_konum_sec(bolge)

    if not konum:
        await query.edit_message_caption(
            f"🚨 *{bolge}* bölgesinde konum kalmadı!\n\n"
            f"`/konum_ekle` ile yeni konum ekleyin.",
            parse_mode="Markdown"
        )
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🚨 *{bolge}* bölgesinde konum tükendi!\n`/konum_ekle` yazarak hemen ekle.",
            parse_mode="Markdown"
        )
        return

    # İşleniyor işaretle
    aktif_siparisler[siparis_no]["durum"] = "isleniyor"
    kaydet(SIPARISLER_DOSYA, aktif_siparisler)

    musteri_id = siparis["user_id"]

    # Müşteriye otomatik gönder
    await context.bot.send_photo(
        chat_id=musteri_id,
        photo=konum["foto_id"],
        caption=(
            f"📦 *Siparişiniz hazırlandı!*\n\n"
            f"Sipariş No: `{siparis_no}`\n"
            f"Aşağıdaki konumdan teslim alabilirsiniz. 📍"
        ),
        parse_mode="Markdown"
    )
    await context.bot.send_location(chat_id=musteri_id, latitude=konum["lat"], longitude=konum["lon"])
    await context.bot.send_message(
        chat_id=musteri_id,
        text=f"✅ *Siparişiniz teslimata hazır!*\n\nSipariş No: `{siparis_no}`\n\nİyi günler! 🎉",
        parse_mode="Markdown"
    )

    # Konumu kullanıldı işaretle
    konumu_kullanildi_isaretle(bolge, konum["id"])

    aktif_siparisler[siparis_no]["durum"]   = "tamamlandi"
    aktif_siparisler[siparis_no]["konum_id"] = konum["id"]
    kaydet(SIPARISLER_DOSYA, aktif_siparisler)

    kalan = bolge_konum_sayisi(bolge)
    uyari = f"\n\n⚠️ *{bolge}* bölgesinde *{kalan}* konum kaldı!" if kalan <= 3 else ""

    await query.edit_message_caption(
        f"✅ *Tamamlandı!* `{siparis_no}`\n📍 `{konum['id']}` gönderildi.{uyari}",
        parse_mode="Markdown"
    )
    logger.info(f"Tamamlandı: {siparis_no} → {konum['id']}")

# ─── ADMİN: /konumlar ───────────────────────────────────────────────────────
async def konumlar_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    mesaj = "📍 *Bölge Konum Durumu*\n─────────────────\n"
    for bolge in BOLGELER.values():
        liste  = konumlar.get(bolge, [])
        toplam = len(liste)
        dolu   = sum(1 for k in liste if k.get("foto_id"))
        kalan  = sum(1 for k in liste if not k.get("kullanildi") and k.get("foto_id"))
        emoji  = "🟢" if kalan > 3 else ("🟡" if kalan > 0 else "🔴")
        mesaj += f"\n{emoji} *{bolge}*: {kalan} kullanılabilir / {toplam} toplam\n"
    mesaj += "\n`/konum_ekle` ile yeni konum ekleyebilirsin."
    await update.message.reply_text(mesaj, parse_mode="Markdown")

# ─── ADMİN: /siparisler ─────────────────────────────────────────────────────
async def admin_siparisler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not aktif_siparisler:
        await update.message.reply_text("📭 Henüz sipariş yok.")
        return
    durum_emoji = {"beklemede": "⏳", "isleniyor": "🔄", "tamamlandi": "✅"}
    mesaj = "📋 *Tüm Siparişler*\n─────────────────\n"
    for no, s in aktif_siparisler.items():
        emoji = durum_emoji.get(s["durum"], "❓")
        mesaj += f"\n{emoji} `{no}` — {s['urun']} | {s['bolge']} | ₺{s['fiyat']}\n"
    await update.message.reply_text(mesaj, parse_mode="Markdown")

# ─── İPTAL / BİLİNMEYEN ────────────────────────────────────────────────────
async def iptal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ İptal edildi. /start ile yeniden başlayın.")
    return ConversationHandler.END

async def bilinmeyen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Sipariş vermek için /start yazın. 👋")

# ─── ANA FONKSİYON ──────────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            URUN_SEC:  [CallbackQueryHandler(urun_sec)],
            BOLGE_SEC: [CallbackQueryHandler(bolge_sec)],
            ODEME:     [CallbackQueryHandler(odeme)],
        },
        fallbacks=[CommandHandler("iptal", iptal)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("siparisler", admin_siparisler))
    app.add_handler(CommandHandler("konumlar",   konumlar_goster))
    app.add_handler(CommandHandler("konum_ekle", konum_ekle_baslat))
    app.add_handler(CallbackQueryHandler(admin_buton_onayla,   pattern=r"^admin_onayla:"))
    app.add_handler(CallbackQueryHandler(konum_ekle_bolge_sec, pattern=r"^konum_ekle_bolge:"))
    app.add_handler(MessageHandler(filters.PHOTO,    foto_al))
    app.add_handler(MessageHandler(filters.LOCATION, konum_al))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bilinmeyen))

    logger.info(f"Bot başlatıldı. Kayıtlı sipariş: {len(aktif_siparisler)}")
    app.run_polling()

if __name__ == "__main__":
    main()
