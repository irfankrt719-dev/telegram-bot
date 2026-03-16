"""
Telegram Sipariş Botu - Ürün Yönetimi + Otomatik Konum
=======================================================
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
BOT_TOKEN = os.environ.get("BOT_TOKEN", "BURAYA_BOT_TOKEN_GIR")
ADMIN_ID  = int(os.environ.get("ADMIN_ID", "123456789"))

BANKA_BILGILERI = """
🏦 *Ödeme Bilgileri*

Banka: Ziraat Bankası
Hesap Adı: Şirket Adı
IBAN: TR00 0000 0000 0000 0000 0000 00

💡 Açıklama kısmına *sipariş numaranızı* yazmayı unutmayın!
"""

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

# Admin işlem durumları
# { admin_id: { "islem": "urun_ekle_ad"|"urun_ekle_fiyat"|"fiyat_guncelle", ... } }
admin_islem = {}
konum_ekleme = {}

# ─── DOSYA İŞLEMLERİ ────────────────────────────────────────────────────────
SIPARISLER_DOSYA = "siparisler.json"
KONUMLAR_DOSYA   = "konumlar.json"
URUNLER_DOSYA    = "urunler.json"

VARSAYILAN_URUNLER = {
    "urun_1": {"ad": "Ürün 1", "fiyat": 50.00},
    "urun_2": {"ad": "Ürün 2", "fiyat": 75.00},
    "urun_3": {"ad": "Ürün 3", "fiyat": 100.00},
}

def yukle(dosya, varsayilan={}):
    if os.path.exists(dosya):
        try:
            with open(dosya, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return varsayilan.copy()
    return varsayilan.copy()

def kaydet(dosya, data):
    with open(dosya, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

aktif_siparisler = yukle(SIPARISLER_DOSYA)
konumlar         = yukle(KONUMLAR_DOSYA, {b: [] for b in BOLGELER.values()})
urunler          = yukle(URUNLER_DOSYA, VARSAYILAN_URUNLER)

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

def urun_id_olustur():
    return f"urun_{int(time.time())}"

# ─── MÜŞTERİ AKIŞI ──────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if not urunler:
        await update.message.reply_text("⚠️ Şu an ürün bulunmuyor. Lütfen daha sonra tekrar deneyin.")
        return ConversationHandler.END
    keyboard = [
        [InlineKeyboardButton(f"🍬 {v['ad']}  –  ₺{v['fiyat']:.2f}", callback_data=k)]
        for k, v in urunler.items()
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
    urun = urunler.get(query.data)
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
                    for k, v in urunler.items()]
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

# ─── ÜRÜN YÖNETİMİ ──────────────────────────────────────────────────────────
async def urun_yonetim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await urun_listesi_goster(update, context)

async def urun_listesi_goster(update_or_query, context, mesaj_guncelle=False):
    keyboard = []
    for kid, u in urunler.items():
        keyboard.append([
            InlineKeyboardButton(f"🍬 {u['ad']} – ₺{u['fiyat']:.2f}", callback_data=f"urun_detay:{kid}"),
        ])
    keyboard.append([InlineKeyboardButton("➕ Yeni Ürün Ekle", callback_data="urun_ekle")])

    mesaj = "🛍 *Ürün Yönetimi*\n─────────────────\nBir ürüne tıklayarak düzenle veya sil.\n➕ ile yeni ürün ekle."

    if mesaj_guncelle and hasattr(update_or_query, 'edit_message_text'):
        await update_or_query.edit_message_text(mesaj, parse_mode="Markdown",
                                                 reply_markup=InlineKeyboardMarkup(keyboard))
    elif hasattr(update_or_query, 'message'):
        await update_or_query.message.reply_text(mesaj, parse_mode="Markdown",
                                                  reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update_or_query.reply_text(mesaj, parse_mode="Markdown",
                                          reply_markup=InlineKeyboardMarkup(keyboard))

async def urun_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Yetkisiz!", show_alert=True)
        return
    await query.answer()
    data = query.data

    # ── Ürün detay ──
    if data.startswith("urun_detay:"):
        kid = data.split(":")[1]
        u   = urunler.get(kid)
        if not u:
            await query.edit_message_text("⚠️ Ürün bulunamadı.")
            return
        keyboard = [
            [InlineKeyboardButton("✏️ Adı Değiştir",   callback_data=f"urun_ad:{kid}")],
            [InlineKeyboardButton("💰 Fiyatı Değiştir", callback_data=f"urun_fiyat:{kid}")],
            [InlineKeyboardButton("🗑 Ürünü Sil",       callback_data=f"urun_sil:{kid}")],
            [InlineKeyboardButton("⬅️ Geri",            callback_data="urun_geri")],
        ]
        await query.edit_message_text(
            f"🍬 *{u['ad']}*\n💰 Fiyat: ₺{u['fiyat']:.2f}\n\nNe yapmak istiyorsun?",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # ── Geri ──
    elif data == "urun_geri":
        await urun_listesi_goster(query, context, mesaj_guncelle=True)

    # ── Yeni ürün ekle ──
    elif data == "urun_ekle":
        admin_islem[ADMIN_ID] = {"islem": "urun_ekle_ad"}
        await query.edit_message_text(
            "➕ *Yeni Ürün Ekleniyor*\n\nÜrünün *adını* yaz:",
            parse_mode="Markdown"
        )

    # ── Ad değiştir ──
    elif data.startswith("urun_ad:"):
        kid = data.split(":")[1]
        admin_islem[ADMIN_ID] = {"islem": "urun_ad_guncelle", "kid": kid}
        u = urunler.get(kid, {})
        await query.edit_message_text(
            f"✏️ *{u.get('ad','')}* için yeni adı yaz:",
            parse_mode="Markdown"
        )

    # ── Fiyat değiştir ──
    elif data.startswith("urun_fiyat:"):
        kid = data.split(":")[1]
        admin_islem[ADMIN_ID] = {"islem": "urun_fiyat_guncelle", "kid": kid}
        u = urunler.get(kid, {})
        await query.edit_message_text(
            f"💰 *{u.get('ad','')}* için yeni fiyatı yaz _(sadece sayı, örn: 75.50)_:",
            parse_mode="Markdown"
        )

    # ── Ürün sil ──
    elif data.startswith("urun_sil:"):
        kid = data.split(":")[1]
        u   = urunler.pop(kid, None)
        if u:
            kaydet(URUNLER_DOSYA, urunler)
            await query.edit_message_text(
                f"🗑 *{u['ad']}* silindi!",
                parse_mode="Markdown"
            )
            await urun_listesi_goster(query, context, mesaj_guncelle=False)
        else:
            await query.edit_message_text("⚠️ Ürün bulunamadı.")

# ─── ADMIN METİN İŞLE ───────────────────────────────────────────────────────
async def admin_metin_isle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    metin   = update.message.text.strip()

    if user_id == ADMIN_ID and user_id in admin_islem:
        islem = admin_islem[user_id]

        # Yeni ürün - ad
        if islem["islem"] == "urun_ekle_ad":
            admin_islem[user_id] = {"islem": "urun_ekle_fiyat", "ad": metin}
            await update.message.reply_text(
                f"✅ Ad: *{metin}*\n\nŞimdi *fiyatı* yaz _(örn: 75.50)_:",
                parse_mode="Markdown"
            )
            return

        # Yeni ürün - fiyat
        elif islem["islem"] == "urun_ekle_fiyat":
            try:
                fiyat = float(metin.replace(",", "."))
                kid   = urun_id_olustur()
                urunler[kid] = {"ad": islem["ad"], "fiyat": fiyat}
                kaydet(URUNLER_DOSYA, urunler)
                del admin_islem[user_id]
                await update.message.reply_text(
                    f"✅ *{islem['ad']}* ₺{fiyat:.2f} fiyatıyla eklendi!",
                    parse_mode="Markdown"
                )
                await urun_listesi_goster(update, context)
            except ValueError:
                await update.message.reply_text("⚠️ Geçersiz fiyat! Sadece sayı gir, örn: *75.50*",
                                                 parse_mode="Markdown")
            return

        # Ad güncelle
        elif islem["islem"] == "urun_ad_guncelle":
            kid = islem["kid"]
            if kid in urunler:
                eski = urunler[kid]["ad"]
                urunler[kid]["ad"] = metin
                kaydet(URUNLER_DOSYA, urunler)
                del admin_islem[user_id]
                await update.message.reply_text(
                    f"✅ *{eski}* → *{metin}* olarak güncellendi!",
                    parse_mode="Markdown"
                )
                await urun_listesi_goster(update, context)
            return

        # Fiyat güncelle
        elif islem["islem"] == "urun_fiyat_guncelle":
            kid = islem["kid"]
            try:
                fiyat = float(metin.replace(",", "."))
                if kid in urunler:
                    eski  = urunler[kid]["fiyat"]
                    urunler[kid]["fiyat"] = fiyat
                    kaydet(URUNLER_DOSYA, urunler)
                    del admin_islem[user_id]
                    await update.message.reply_text(
                        f"✅ *{urunler[kid]['ad']}* fiyatı ₺{eski:.2f} → ₺{fiyat:.2f} güncellendi!",
                        parse_mode="Markdown"
                    )
                    await urun_listesi_goster(update, context)
            except ValueError:
                await update.message.reply_text("⚠️ Geçersiz fiyat! Sadece sayı gir, örn: *75.50*",
                                                 parse_mode="Markdown")
            return

    # Müşteri mesajı
    await update.message.reply_text("Sipariş vermek için /start yazın. 👋")

# ─── DEKONT GELDİĞİNDE ──────────────────────────────────────────────────────
async def foto_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id == ADMIN_ID:
        if user_id in konum_ekleme and konum_ekleme[user_id]["adim"] == "foto":
            konum_ekleme[user_id]["foto_id"] = update.message.photo[-1].file_id
            konum_ekleme[user_id]["adim"]    = "konum"
            bolge = konum_ekleme[user_id]["bolge"]
            await update.message.reply_text(
                f"✅ Fotoğraf kaydedildi!\n\nŞimdi *{bolge}* için 📍 *konumu* gönder:",
                parse_mode="Markdown"
            )
        else:
            foto_id = update.message.photo[-1].file_id
            await update.message.reply_text(f"📋 *Fotoğraf ID:*\n`{foto_id}`", parse_mode="Markdown")
        return

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
            f"💰 *Yeni Dekont!*\n\n🔖 `{siparis_no}`\n"
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
    if user_id in konum_ekleme and konum_ekleme[user_id]["adim"] == "konum":
        akis    = konum_ekleme[user_id]
        bolge   = akis["bolge"]
        foto_id = akis["foto_id"]
        lat     = update.message.location.latitude
        lon     = update.message.location.longitude
        konum_id = f"{bolge.lower().replace(' ','_')}_{int(time.time())}"
        if bolge not in konumlar:
            konumlar[bolge] = []
        konumlar[bolge].append({"id": konum_id, "lat": lat, "lon": lon,
                                  "foto_id": foto_id, "kullanildi": False})
        kaydet(KONUMLAR_DOSYA, konumlar)
        del konum_ekleme[user_id]
        kalan = bolge_konum_sayisi(bolge)
        await update.message.reply_text(
            f"✅ *{bolge}* bölgesine konum eklendi!\n📍 `{lat:.4f}, {lon:.4f}`\n"
            f"Kullanılabilir konum: *{kalan}*",
            parse_mode="Markdown"
        )
        return
    await update.message.reply_text("Konum alındı ama aktif işlem yok.")

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
            f"🚨 *{bolge}* bölgesinde konum kalmadı!\n`/konum_ekle` ile ekleyin.",
            parse_mode="Markdown"
        )
        return
    aktif_siparisler[siparis_no]["durum"] = "isleniyor"
    kaydet(SIPARISLER_DOSYA, aktif_siparisler)
    musteri_id = siparis["user_id"]
    await context.bot.send_photo(
        chat_id=musteri_id, photo=konum["foto_id"],
        caption=f"📦 *Siparişiniz hazırlandı!*\n\nSipariş No: `{siparis_no}`\nAşağıdaki konumdan teslim alabilirsiniz. 📍",
        parse_mode="Markdown"
    )
    await context.bot.send_location(chat_id=musteri_id, latitude=konum["lat"], longitude=konum["lon"])
    await context.bot.send_message(
        chat_id=musteri_id,
        text=f"✅ *Siparişiniz teslimata hazır!*\n\nSipariş No: `{siparis_no}`\n\nİyi günler! 🎉",
        parse_mode="Markdown"
    )
    konumu_kullanildi_isaretle(bolge, konum["id"])
    aktif_siparisler[siparis_no]["durum"] = "tamamlandi"
    kaydet(SIPARISLER_DOSYA, aktif_siparisler)
    kalan = bolge_konum_sayisi(bolge)
    uyari = f"\n\n⚠️ *{bolge}* bölgesinde *{kalan}* konum kaldı!" if kalan <= 3 else ""
    await query.edit_message_caption(
        f"✅ *Tamamlandı!* `{siparis_no}`\n📍 `{konum['id']}` gönderildi.{uyari}",
        parse_mode="Markdown"
    )

# ─── ADMİN: /konum_ekle ─────────────────────────────────────────────────────
async def konum_ekle_baslat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    keyboard = [
        [InlineKeyboardButton(f"📌 {ad}", callback_data=f"konum_ekle_bolge:{ad}")]
        for ad in BOLGELER.values()
    ]
    await update.message.reply_text("Hangi bölgeye konum eklemek istiyorsun?",
                                     reply_markup=InlineKeyboardMarkup(keyboard))

async def konum_ekle_bolge_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Yetkisiz!", show_alert=True)
        return
    await query.answer()
    bolge = query.data.split(":")[1]
    konum_ekleme[ADMIN_ID] = {"adim": "foto", "bolge": bolge, "foto_id": None}
    await query.edit_message_text(
        f"📍 *{bolge}* bölgesine konum ekleniyor\n\n*Adım 1:* Fotoğrafı gönder 📸",
        parse_mode="Markdown"
    )

# ─── ADMİN: /konumlar ───────────────────────────────────────────────────────
async def konumlar_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    mesaj = "📍 *Bölge Konum Durumu*\n─────────────────\n"
    for bolge in BOLGELER.values():
        liste  = konumlar.get(bolge, [])
        kalan  = sum(1 for k in liste if not k.get("kullanildi") and k.get("foto_id"))
        emoji  = "🟢" if kalan > 3 else ("🟡" if kalan > 0 else "🔴")
        mesaj += f"\n{emoji} *{bolge}*: {kalan} kullanılabilir / {len(liste)} toplam\n"
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

# ─── İPTAL ──────────────────────────────────────────────────────────────────
async def iptal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ İptal edildi. /start ile yeniden başlayın.")
    return ConversationHandler.END

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
    app.add_handler(CommandHandler("urunler",    urun_yonetim))
    app.add_handler(CallbackQueryHandler(admin_buton_onayla,   pattern=r"^admin_onayla:"))
    app.add_handler(CallbackQueryHandler(konum_ekle_bolge_sec, pattern=r"^konum_ekle_bolge:"))
    app.add_handler(CallbackQueryHandler(urun_callback,        pattern=r"^urun_"))
    app.add_handler(MessageHandler(filters.PHOTO,    foto_al))
    app.add_handler(MessageHandler(filters.LOCATION, konum_al))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_metin_isle))
    logger.info(f"Bot başlatıldı. Ürün: {len(urunler)} | Sipariş: {len(aktif_siparisler)}")
    app.run_polling()

if __name__ == "__main__":
    main()
