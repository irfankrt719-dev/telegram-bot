"""
Telegram Sipariş Botu - Konum Bazlı Sistem
==========================================
Kurulum:  pip install python-telegram-bot --upgrade
Çalıştır: python bot.py

Veri yapısı:
konumlar.json → { "İstanbul": { "Kadıköy": [ {konum_obj}, ... ] } }
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

BANKA_BILGILERI = (
    "Odeme Bilgileri\n"
    "─────────────────\n"
    "Banka: Ziraat Bankasi\n"
    "Hesap Adi: Sirket Adi\n"
    "IBAN: TR00 0000 0000 0000 0000 0000 00\n\n"
    "Aciklama kismina siparis numaranizi yazmayi unutmayin!"
)

# Musteri adim sabitleri
IL_SEC, ILCE_SEC, URUN_SEC, GRAM_SEC, ODEME = range(5)

# Admin islem durumu
admin_islem  = {}  # { admin_id: { "adim": ..., ... } }

# ─── DOSYALAR ───────────────────────────────────────────────────────────────
SIPARISLER_DOSYA = "siparisler.json"
KONUMLAR_DOSYA   = "konumlar.json"

def yukle(dosya, varsayilan):
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

# konumlar yapisi:
# {
#   "Istanbul": {
#     "Kadikoy": [
#       {
#         "id": "...",
#         "lat": 40.99,
#         "lon": 29.02,
#         "foto_id": "...",
#         "kullanildi": false,
#         "urunler": {
#           "urun_id": { "ad": "Urun A", "gramlar": { "100g": 50.0, "250g": 110.0 } }
#         }
#       }
#     ]
#   }
# }

aktif_siparisler = yukle(SIPARISLER_DOSYA, {})
konumlar         = yukle(KONUMLAR_DOSYA, {})

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── YARDIMCI ───────────────────────────────────────────────────────────────
def siparis_no_olustur(user_id):
    return f"SP{user_id % 10000:04d}{int(time.time()) % 10000:04d}"

def ilce_musait_konum(il, ilce):
    """İlçedeki ilk kullanılmamış ve ürünü olan konumu döner."""
    for k in konumlar.get(il, {}).get(ilce, []):
        if not k.get("kullanildi") and k.get("foto_id") and k.get("urunler"):
            return k
    return None

def ilce_urunleri(il, ilce):
    """İlçedeki tüm aktif konumların ürünlerini birleştirir."""
    urunler = {}
    for k in konumlar.get(il, {}).get(ilce, []):
        if not k.get("kullanildi") and k.get("foto_id"):
            for uid, u in k.get("urunler", {}).items():
                if uid not in urunler:
                    urunler[uid] = u
    return urunler

def ilce_konum_sayisi(il, ilce):
    return sum(1 for k in konumlar.get(il, {}).get(ilce, [])
               if not k.get("kullanildi") and k.get("foto_id"))

def konum_id_olustur(il, ilce):
    return f"{il}_{ilce}_{int(time.time())}".replace(" ", "_").lower()

# ─── MÜŞTERİ: İL SEÇİMİ ────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    aktif_iller = [il for il, ilceler in konumlar.items()
                   if any(ilce_konum_sayisi(il, ilce) > 0 for ilce in ilceler)]

    if not aktif_iller:
        await update.message.reply_text(
            "Su an hizmet verdigimiz bir bolge bulunmuyor.\nLutfen daha sonra tekrar deneyin."
        )
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(f"📍 {il}", callback_data=f"il:{il}")]
        for il in aktif_iller
    ]
    keyboard.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])

    await update.message.reply_text(
        f"Merhaba {update.effective_user.first_name}!\n\nHizmet verdigimiz ili secin:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return IL_SEC

# ─── MÜŞTERİ: İL SEÇİLDİ ───────────────────────────────────────────────────
async def il_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "iptal":
        await query.edit_message_text("Iptal edildi. /start ile yeniden baslayin.")
        return ConversationHandler.END

    il = query.data.split(":", 1)[1]
    context.user_data["il"] = il

    aktif_ilceler = [ilce for ilce in konumlar.get(il, {})
                     if ilce_konum_sayisi(il, ilce) > 0]

    if not aktif_ilceler:
        await query.edit_message_text(f"{il} ilinde su an musait bolge yok.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(f"📌 {ilce}", callback_data=f"ilce:{ilce}")]
        for ilce in aktif_ilceler
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_il")])
    keyboard.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])

    await query.edit_message_text(
        f"Il: {il}\n\nBolgenizi secin:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ILCE_SEC

# ─── MÜŞTERİ: İLÇE SEÇİLDİ ─────────────────────────────────────────────────
async def ilce_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "iptal":
        await query.edit_message_text("Iptal edildi.")
        return ConversationHandler.END

    if query.data == "geri_il":
        aktif_iller = [il for il, ilceler in konumlar.items()
                       if any(ilce_konum_sayisi(il, ilce) > 0 for ilce in ilceler)]
        keyboard = [[InlineKeyboardButton(f"📍 {il}", callback_data=f"il:{il}")] for il in aktif_iller]
        keyboard.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])
        await query.edit_message_text("Ili secin:", reply_markup=InlineKeyboardMarkup(keyboard))
        return IL_SEC

    ilce = query.data.split(":", 1)[1]
    il   = context.user_data["il"]
    context.user_data["ilce"] = ilce

    urunler = ilce_urunleri(il, ilce)
    if not urunler:
        await query.edit_message_text(f"{ilce} bolgesinde su an urun bulunmuyor.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(f"🍬 {u['ad']}", callback_data=f"urun:{uid}")]
        for uid, u in urunler.items()
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_ilce")])
    keyboard.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])

    await query.edit_message_text(
        f"Il: {il}\nBolge: {ilce}\n\nUrun secin:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return URUN_SEC

# ─── MÜŞTERİ: ÜRÜN SEÇİLDİ ─────────────────────────────────────────────────
async def urun_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "iptal":
        await query.edit_message_text("Iptal edildi.")
        return ConversationHandler.END

    if query.data == "geri_ilce":
        il = context.user_data["il"]
        aktif_ilceler = [ilce for ilce in konumlar.get(il, {})
                         if ilce_konum_sayisi(il, ilce) > 0]
        keyboard = [[InlineKeyboardButton(f"📌 {ilce}", callback_data=f"ilce:{ilce}")] for ilce in aktif_ilceler]
        keyboard.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_il")])
        keyboard.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])
        await query.edit_message_text("Bolgenizi secin:", reply_markup=InlineKeyboardMarkup(keyboard))
        return ILCE_SEC

    uid  = query.data.split(":", 1)[1]
    il   = context.user_data["il"]
    ilce = context.user_data["ilce"]

    urunler = ilce_urunleri(il, ilce)
    urun    = urunler.get(uid)
    if not urun:
        await query.edit_message_text("Urun bulunamadi.")
        return ConversationHandler.END

    context.user_data["urun_id"] = uid
    context.user_data["urun_ad"] = urun["ad"]

    gramlar = urun.get("gramlar", {})
    keyboard = [
        [InlineKeyboardButton(f"{gram}  —  {fiyat}", callback_data=f"gram:{gram}:{fiyat}")]
        for gram, fiyat in gramlar.items()
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_urun")])
    keyboard.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])

    await query.edit_message_text(
        f"Il: {il}\nBolge: {ilce}\nUrun: {urun['ad']}\n\nMiktar secin:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return GRAM_SEC

# ─── MÜŞTERİ: GRAM SEÇİLDİ ─────────────────────────────────────────────────
async def gram_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "iptal":
        await query.edit_message_text("Iptal edildi.")
        return ConversationHandler.END

    if query.data == "geri_urun":
        il    = context.user_data["il"]
        ilce  = context.user_data["ilce"]
        urunler = ilce_urunleri(il, ilce)
        keyboard = [[InlineKeyboardButton(f"🍬 {u['ad']}", callback_data=f"urun:{uid}")] for uid, u in urunler.items()]
        keyboard.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_ilce")])
        keyboard.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])
        await query.edit_message_text("Urun secin:", reply_markup=InlineKeyboardMarkup(keyboard))
        return URUN_SEC

    parcalar = query.data.split(":")
    gram     = parcalar[1]
    fiyat    = float(parcalar[2])

    context.user_data["gram"]  = gram
    context.user_data["fiyat"] = fiyat

    il       = context.user_data["il"]
    ilce     = context.user_data["ilce"]
    urun_ad  = context.user_data["urun_ad"]
    siparis_no = siparis_no_olustur(update.effective_user.id)
    context.user_data["siparis_no"] = siparis_no

    ozet = (
        f"Siparis Ozeti\n"
        f"─────────────────\n"
        f"Siparis No : {siparis_no}\n"
        f"Il         : {il}\n"
        f"Bolge      : {ilce}\n"
        f"Urun       : {urun_ad}\n"
        f"Miktar     : {gram}\n"
        f"Fiyat      : {fiyat}\n"
        f"─────────────────\n\n"
        f"{BANKA_BILGILERI}\n\n"
        f"Odemeyi yaptiktan sonra dekont fotografini gonderin."
    )

    keyboard = [
        [InlineKeyboardButton("✅ Siparisi Onayla", callback_data="onayla")],
        [InlineKeyboardButton("⬅️ Geri",            callback_data="geri_gram")],
        [InlineKeyboardButton("❌ İptal",            callback_data="iptal")],
    ]
    await query.edit_message_text(ozet, reply_markup=InlineKeyboardMarkup(keyboard))
    return ODEME

# ─── MÜŞTERİ: ÖDEME ─────────────────────────────────────────────────────────
async def odeme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "iptal":
        await query.edit_message_text("Iptal edildi.")
        return ConversationHandler.END

    if query.data == "geri_gram":
        uid  = context.user_data["urun_id"]
        il   = context.user_data["il"]
        ilce = context.user_data["ilce"]
        urunler = ilce_urunleri(il, ilce)
        urun    = urunler.get(uid, {})
        gramlar = urun.get("gramlar", {})
        keyboard = [
            [InlineKeyboardButton(f"{gram}  —  {fiyat}", callback_data=f"gram:{gram}:{fiyat}")]
            for gram, fiyat in gramlar.items()
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_urun")])
        keyboard.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])
        await query.edit_message_text("Miktar secin:", reply_markup=InlineKeyboardMarkup(keyboard))
        return GRAM_SEC

    if query.data == "onayla":
        siparis_no = context.user_data.get("siparis_no", "?")
        aktif_siparisler[siparis_no] = {
            "user_id": update.effective_user.id,
            "il":      context.user_data.get("il"),
            "ilce":    context.user_data.get("ilce"),
            "urun":    f"{context.user_data.get('urun_ad')} {context.user_data.get('gram')}",
            "fiyat":   context.user_data.get("fiyat"),
            "durum":   "beklemede"
        }
        kaydet(SIPARISLER_DOSYA, aktif_siparisler)

        await query.edit_message_text(
            f"Siparisıniz alindi!\n\n"
            f"Siparis No: {siparis_no}\n\n"
            f"Havale/EFT islemini gerceklestirip dekontu gonderin.\n\nTesekkurler!"
        )
        return ConversationHandler.END

# ─── DEKONT GELDİĞİNDE ──────────────────────────────────────────────────────
async def foto_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Admin foto isliyor mu?
    if user_id == ADMIN_ID:
        if user_id in admin_islem and admin_islem[user_id].get("adim") == "foto":
            admin_islem[user_id]["foto_id"] = update.message.photo[-1].file_id
            admin_islem[user_id]["adim"]    = "konum"
            await update.message.reply_text(
                "Fotograf kaydedildi!\n\nSimdi konumu gonder (Telegram'dan konum paylasimini kullan):"
            )
        else:
            foto_id = update.message.photo[-1].file_id
            await update.message.reply_text(f"Fotograf ID:\n{foto_id}")
        return

    # Musteri dekont gonderiyor
    siparis_no = context.user_data.get("siparis_no")
    if not siparis_no:
        for no, s in aktif_siparisler.items():
            if str(s["user_id"]) == str(user_id) and s["durum"] == "beklemede":
                siparis_no = no
                break

    if not siparis_no:
        await update.message.reply_text("Aktif siparisıniz yok. /start ile baslayin.")
        return

    siparis  = aktif_siparisler.get(siparis_no, {})
    keyboard = [[InlineKeyboardButton(
        f"Onayla — {siparis_no}",
        callback_data=f"admin_onayla:{siparis_no}"
    )]]

    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=update.message.photo[-1].file_id,
        caption=(
            f"Yeni Dekont!\n\n"
            f"Siparis No: {siparis_no}\n"
            f"Il: {siparis.get('il','?')} / {siparis.get('ilce','?')}\n"
            f"Urun: {siparis.get('urun','?')}\n"
            f"Fiyat: {siparis.get('fiyat','?')}\n\n"
            f"Onaylamak icin butona bas:"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text(
        f"Dekontunuz alindi! Siparis No: {siparis_no}\nEn kisa surede onay gonderilecektir."
    )

# ─── KONUM GELDİĞİNDE ───────────────────────────────────────────────────────
async def konum_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return

    if user_id in admin_islem and admin_islem[user_id].get("adim") == "konum":
        islem   = admin_islem[user_id]
        il      = islem["il"]
        ilce    = islem["ilce"]
        foto_id = islem["foto_id"]
        lat     = update.message.location.latitude
        lon     = update.message.location.longitude

        # Konumu oluştur
        yeni_konum = {
            "id":        konum_id_olustur(il, ilce),
            "lat":       lat,
            "lon":       lon,
            "foto_id":   foto_id,
            "kullanildi": False,
            "urunler":   {}
        }

        if il not in konumlar:
            konumlar[il] = {}
        if ilce not in konumlar[il]:
            konumlar[il][ilce] = []

        konumlar[il][ilce].append(yeni_konum)
        kaydet(KONUMLAR_DOSYA, konumlar)

        # Ürün ekleme adımına geç
        konum_idx = len(konumlar[il][ilce]) - 1
        admin_islem[user_id] = {
            "adim":      "urun_ad",
            "il":        il,
            "ilce":      ilce,
            "konum_idx": konum_idx
        }

        await update.message.reply_text(
            f"Konum kaydedildi!\n\n"
            f"Simdi bu konuma urun ekleyelim.\n"
            f"Urun adini yaz (örn: Esrar, Skunk, Crystall):"
        )
        return

    await update.message.reply_text("Konum alindi ama aktif islem yok.")

# ─── ADMİN METİN İŞLE ───────────────────────────────────────────────────────
async def admin_metin_isle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    metin   = update.message.text.strip()

    if user_id == ADMIN_ID and user_id in admin_islem:
        islem = admin_islem[user_id]
        adim  = islem.get("adim")

        # Ürün adı
        if adim == "urun_ad":
            admin_islem[user_id]["urun_ad"]  = metin
            admin_islem[user_id]["urun_id"]  = f"urun_{int(time.time())}"
            admin_islem[user_id]["gramlar"]  = {}
            admin_islem[user_id]["adim"]     = "gram_miktar"
            await update.message.reply_text(
                f"Urun: {metin}\n\nGram miktarini yaz (örn: 1g, 3.5g, 7g, 14g):"
            )
            return

        # Gram miktarı
        elif adim == "gram_miktar":
            admin_islem[user_id]["gecici_gram"] = metin
            admin_islem[user_id]["adim"]        = "gram_fiyat"
            await update.message.reply_text(f"{metin} icin fiyati yaz (örn: 150):")
            return

        # Gram fiyatı
        elif adim == "gram_fiyat":
            try:
                fiyat = float(metin.replace(",", "."))
                gram  = admin_islem[user_id]["gecici_gram"]
                admin_islem[user_id]["gramlar"][gram] = fiyat
                admin_islem[user_id]["adim"] = "gram_devam"

                gramlar    = admin_islem[user_id]["gramlar"]
                gram_metni = "\n".join([f"  {g}: {f}" for g, f in gramlar.items()])

                keyboard = [
                    [InlineKeyboardButton("➕ Baska Gram Ekle", callback_data="admin_gram_ekle")],
                    [InlineKeyboardButton("✅ Kaydet",           callback_data="admin_kaydet")],
                ]
                await update.message.reply_text(
                    f"Eklendi!\n\nMevcut gramlar:\n{gram_metni}",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except ValueError:
                await update.message.reply_text("Gecersiz fiyat! Sadece sayi gir, örn: 150")
            return

    await update.message.reply_text("Siparis vermek icin /start yazin.")

# ─── ADMİN CALLBACK ─────────────────────────────────────────────────────────
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("Yetkisiz!", show_alert=True)
        return
    await query.answer()
    data = query.data

    # Gram devam
    if data == "admin_gram_ekle":
        admin_islem[ADMIN_ID]["adim"] = "gram_miktar"
        await query.edit_message_text("Yeni gram miktarini yaz (örn: 28g):")

    # Kaydet
    elif data == "admin_kaydet":
        islem     = admin_islem.get(ADMIN_ID, {})
        il        = islem["il"]
        ilce      = islem["ilce"]
        konum_idx = islem["konum_idx"]
        urun_id   = islem["urun_id"]
        urun_ad   = islem["urun_ad"]
        gramlar   = islem["gramlar"]

        konumlar[il][ilce][konum_idx]["urunler"][urun_id] = {
            "ad":     urun_ad,
            "gramlar": gramlar
        }
        kaydet(KONUMLAR_DOSYA, konumlar)

        gram_metni = "\n".join([f"  {g}: {f}" for g, f in gramlar.items()])
        kalan      = ilce_konum_sayisi(il, ilce)

        keyboard = [
            [InlineKeyboardButton("➕ Bu Konuma Urun Ekle",   callback_data=f"konum_urun_ekle:{il}:{ilce}:{konum_idx}")],
            [InlineKeyboardButton("✅ Tamamlandi",             callback_data="admin_tamam")],
        ]

        del admin_islem[ADMIN_ID]
        await query.edit_message_text(
            f"Kaydedildi!\n\n"
            f"Il: {il} / Ilce: {ilce}\n"
            f"Urun: {urun_ad}\n"
            f"Gramlar:\n{gram_metni}\n\n"
            f"Bu ilcede toplam {kalan} aktif konum var.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "admin_tamam":
        await query.edit_message_text("Tamamlandi! /konum_ekle ile yeni konum ekleyebilirsin.")

    elif data.startswith("konum_urun_ekle:"):
        parcalar  = data.split(":")
        il        = parcalar[1]
        ilce      = parcalar[2]
        konum_idx = int(parcalar[3])
        admin_islem[ADMIN_ID] = {
            "adim":      "urun_ad",
            "il":        il,
            "ilce":      ilce,
            "konum_idx": konum_idx,
            "gramlar":   {}
        }
        await query.edit_message_text("Urun adini yaz:")

    # Sipariş onayla
    elif data.startswith("admin_onayla:"):
        siparis_no = data.split(":")[1]
        siparis    = aktif_siparisler.get(siparis_no)

        if not siparis:
            await query.edit_message_caption(f"{siparis_no} bulunamadi.")
            return
        if siparis["durum"] in ("isleniyor", "tamamlandi"):
            await query.answer(f"Bu siparis zaten {siparis['durum']}!", show_alert=True)
            return

        il   = siparis["il"]
        ilce = siparis["ilce"]
        konum = ilce_musait_konum(il, ilce)

        if not konum:
            await query.edit_message_caption(
                f"{il}/{ilce} bolgesinde musait konum kalmadi!\n/konum_ekle ile ekleyin."
            )
            return

        aktif_siparisler[siparis_no]["durum"] = "isleniyor"
        kaydet(SIPARISLER_DOSYA, aktif_siparisler)

        musteri_id = siparis["user_id"]

        await context.bot.send_photo(
            chat_id=musteri_id,
            photo=konum["foto_id"],
            caption=(
                f"Siparisıniz hazirlandi!\n\n"
                f"Siparis No: {siparis_no}\n"
                f"Asagidaki konumdan teslim alabilirsiniz."
            )
        )
        await context.bot.send_location(
            chat_id=musteri_id,
            latitude=konum["lat"],
            longitude=konum["lon"]
        )
        await context.bot.send_message(
            chat_id=musteri_id,
            text=f"Siparisıniz teslimata hazir!\n\nSiparis No: {siparis_no}\n\nIyi gunler!"
        )

        # Konumu kullanıldı işaretle
        for k in konumlar.get(il, {}).get(ilce, []):
            if k["id"] == konum["id"]:
                k["kullanildi"] = True
                break
        kaydet(KONUMLAR_DOSYA, konumlar)

        aktif_siparisler[siparis_no]["durum"] = "tamamlandi"
        kaydet(SIPARISLER_DOSYA, aktif_siparisler)

        kalan = ilce_konum_sayisi(il, ilce)
        uyari = f"\n\n{il}/{ilce} bolgesinde {kalan} konum kaldi!" if kalan <= 3 else ""
        await query.edit_message_caption(f"Tamamlandi! {siparis_no}{uyari}")

# ─── ADMİN: /konum_ekle ─────────────────────────────────────────────────────
async def konum_ekle_baslat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    iller = list(konumlar.keys())
    keyboard = [
        [InlineKeyboardButton(f"📍 {il}", callback_data=f"kekle_il:{il}")]
        for il in iller
    ]
    keyboard.append([InlineKeyboardButton("➕ Yeni Il Ekle", callback_data="kekle_yeni_il")])
    await update.message.reply_text(
        "Konum eklenecek ili sec:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def konum_ekle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("Yetkisiz!", show_alert=True)
        return
    await query.answer()
    data = query.data

    if data == "kekle_yeni_il":
        admin_islem[ADMIN_ID] = {"adim": "yeni_il"}
        await query.edit_message_text("Yeni ilin adini yaz (örn: Istanbul):")

    elif data.startswith("kekle_il:"):
        il     = data.split(":", 1)[1]
        ilceler = list(konumlar.get(il, {}).keys())
        keyboard = [
            [InlineKeyboardButton(f"📌 {ilce}", callback_data=f"kekle_ilce:{il}:{ilce}")]
            for ilce in ilceler
        ]
        keyboard.append([InlineKeyboardButton("➕ Yeni Ilce Ekle", callback_data=f"kekle_yeni_ilce:{il}")])
        await query.edit_message_text(
            f"Il: {il}\n\nIlce sec:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("kekle_yeni_ilce:"):
        il = data.split(":", 1)[1]
        admin_islem[ADMIN_ID] = {"adim": "yeni_ilce", "il": il}
        await query.edit_message_text(f"{il} icin yeni ilce adini yaz:")

    elif data.startswith("kekle_ilce:"):
        parcalar = data.split(":")
        il   = parcalar[1]
        ilce = parcalar[2]
        admin_islem[ADMIN_ID] = {"adim": "foto", "il": il, "ilce": ilce}
        await query.edit_message_text(
            f"Il: {il} / Ilce: {ilce}\n\nAdim 1: Konuma ait fotografi gonder:"
        )

async def konum_ekle_metin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    metin   = update.message.text.strip()

    if user_id != ADMIN_ID or user_id not in admin_islem:
        return False

    islem = admin_islem[user_id]
    adim  = islem.get("adim")

    if adim == "yeni_il":
        if metin not in konumlar:
            konumlar[metin] = {}
            kaydet(KONUMLAR_DOSYA, konumlar)
        iller = list(konumlar.keys())
        keyboard = [[InlineKeyboardButton(f"📍 {il}", callback_data=f"kekle_il:{il}")] for il in iller]
        keyboard.append([InlineKeyboardButton("➕ Yeni Il Ekle", callback_data="kekle_yeni_il")])
        del admin_islem[user_id]
        await update.message.reply_text(
            f"{metin} eklendi! Simdi ili sec:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return True

    elif adim == "yeni_ilce":
        il = islem["il"]
        if il not in konumlar:
            konumlar[il] = {}
        if metin not in konumlar[il]:
            konumlar[il][metin] = []
            kaydet(KONUMLAR_DOSYA, konumlar)
        admin_islem[user_id] = {"adim": "foto", "il": il, "ilce": metin}
        await update.message.reply_text(
            f"Ilce '{metin}' eklendi!\n\nSimdi konuma ait fotografi gonder:"
        )
        return True

    return False

# ─── ADMİN: /konumlar ───────────────────────────────────────────────────────
async def konumlar_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not konumlar:
        await update.message.reply_text("Hic konum yok. /konum_ekle ile ekle.")
        return
    mesaj = "Konum Durumu\n─────────────────\n"
    for il, ilceler in konumlar.items():
        mesaj += f"\n📍 {il}\n"
        for ilce, liste in ilceler.items():
            kalan = sum(1 for k in liste if not k.get("kullanildi") and k.get("foto_id"))
            emoji = "🟢" if kalan > 3 else ("🟡" if kalan > 0 else "🔴")
            mesaj += f"  {emoji} {ilce}: {kalan} aktif / {len(liste)} toplam\n"
    await update.message.reply_text(mesaj)

# ─── ADMİN: /siparisler ─────────────────────────────────────────────────────
async def admin_siparisler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not aktif_siparisler:
        await update.message.reply_text("Henuz siparis yok.")
        return
    durum_emoji = {"beklemede": "⏳", "isleniyor": "🔄", "tamamlandi": "✅"}
    mesaj = "Tum Siparisler\n─────────────────\n"
    for no, s in aktif_siparisler.items():
        emoji = durum_emoji.get(s["durum"], "?")
        mesaj += f"\n{emoji} {no}\n  {s.get('il','')}/{s.get('ilce','')} | {s['urun']} | {s['fiyat']}\n"
    await update.message.reply_text(mesaj)

# ─── İPTAL ──────────────────────────────────────────────────────────────────
async def iptal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Iptal edildi. /start ile yeniden baslayin.")
    return ConversationHandler.END

# ─── GENEL METİN HANDLERi ───────────────────────────────────────────────────
async def metin_isle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id == ADMIN_ID and user_id in admin_islem:
        adim = admin_islem[user_id].get("adim")

        # Konum ekleme metin adımları
        if adim in ("yeni_il", "yeni_ilce"):
            await konum_ekle_metin(update, context)
            return

        # Ürün ekleme metin adımları
        if adim in ("urun_ad", "gram_miktar", "gram_fiyat"):
            await admin_metin_isle(update, context)
            return

    await update.message.reply_text("Siparis vermek icin /start yazin.")

# ─── ANA FONKSİYON ──────────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            IL_SEC:   [CallbackQueryHandler(il_sec)],
            ILCE_SEC: [CallbackQueryHandler(ilce_sec)],
            URUN_SEC: [CallbackQueryHandler(urun_sec)],
            GRAM_SEC: [CallbackQueryHandler(gram_sec)],
            ODEME:    [CallbackQueryHandler(odeme)],
        },
        fallbacks=[CommandHandler("iptal", iptal)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("siparisler", admin_siparisler))
    app.add_handler(CommandHandler("konumlar",   konumlar_goster))
    app.add_handler(CommandHandler("konum_ekle", konum_ekle_baslat))

    app.add_handler(CallbackQueryHandler(admin_callback,       pattern=r"^(admin_onayla:|admin_gram_ekle|admin_kaydet|admin_tamam|konum_urun_ekle:)"))
    app.add_handler(CallbackQueryHandler(konum_ekle_callback,  pattern=r"^(kekle_)"))

    app.add_handler(MessageHandler(filters.PHOTO,    foto_al))
    app.add_handler(MessageHandler(filters.LOCATION, konum_al))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, metin_isle))

    logger.info(f"Bot basladi. Siparis: {len(aktif_siparisler)}")
    app.run_polling()

if __name__ == "__main__":
    main()
