"""
Telegram Sipariş Botu - Konum Bazlı + Merkezi Ürün Havuzu
=========================================================
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

BANKA_BILGILERI = (
    "Odeme Bilgileri\n"
    "─────────────────\n"
    "Banka: Ziraat Bankasi\n"
    "Hesap Adi: Sirket Adi\n"
    "IBAN: TR00 0000 0000 0000 0000 0000 00\n\n"
    "Aciklama kismina siparis numaranizi yazmayi unutmayin!"
)

IL_SEC, ILCE_SEC, URUN_SEC, GRAM_SEC, ODEME = range(5)

admin_islem = {}

# ─── DOSYALAR ───────────────────────────────────────────────────────────────
SIPARISLER_DOSYA = "siparisler.json"
KONUMLAR_DOSYA   = "konumlar.json"
URUN_HAVUZU_DOSYA = "urun_havuzu.json"

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
#         "lat": 40.99, "lon": 29.02,
#         "foto_id": "...",
#         "kullanildi": false,
#         "urunler": {
#           "havuz_urun_id": {
#             "ad": "Skunk",
#             "gramlar": { "1g": 150, "3.5g": 450 }
#           }
#         }
#       }
#     ]
#   }
# }

# urun_havuzu yapisi:
# { "uid1": "Skunk", "uid2": "Crystall", ... }

VARSAYILAN_URUN_HAVUZU = {
    "u_demo1": "Skunk",
    "u_demo2": "Crystall",
    "u_demo3": "Pollem"
}

aktif_siparisler = yukle(SIPARISLER_DOSYA, {})
konumlar         = yukle(KONUMLAR_DOSYA, {})
urun_havuzu      = yukle(URUN_HAVUZU_DOSYA, VARSAYILAN_URUN_HAVUZU)

if not os.path.exists(URUN_HAVUZU_DOSYA):
    kaydet(URUN_HAVUZU_DOSYA, urun_havuzu)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── YARDIMCI ───────────────────────────────────────────────────────────────
def siparis_no_olustur(user_id):
    return f"SP{user_id % 10000:04d}{int(time.time()) % 10000:04d}"

def urun_id_olustur():
    return f"u{int(time.time())}"

def konum_id_olustur():
    return f"k{int(time.time())}"

def ilce_musait_konum(il, ilce):
    for k in konumlar.get(il, {}).get(ilce, []):
        if not k.get("kullanildi") and k.get("foto_id") and k.get("urunler"):
            return k
    return None

def ilce_urunleri_birlestir(il, ilce):
    """İlçedeki tüm aktif konumların ürünlerini döner."""
    sonuc = {}
    for k in konumlar.get(il, {}).get(ilce, []):
        if not k.get("kullanildi") and k.get("foto_id"):
            for uid, u in k.get("urunler", {}).items():
                if uid not in sonuc:
                    sonuc[uid] = u
    return sonuc

def ilce_konum_sayisi(il, ilce):
    return sum(1 for k in konumlar.get(il, {}).get(ilce, [])
               if not k.get("kullanildi") and k.get("foto_id"))

# ─── MÜŞTERİ AKIŞI ──────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    aktif_iller = [il for il, ilceler in konumlar.items()
                   if any(ilce_konum_sayisi(il, ilce) > 0 for ilce in ilceler)]
    if not aktif_iller:
        await update.message.reply_text(
            "Su an hizmet verdigimiz bir bolge bulunmuyor.\nLutfen daha sonra tekrar deneyin."
        )
        return ConversationHandler.END
    keyboard = [[InlineKeyboardButton(f"📍 {il}", callback_data=f"il:{il}")] for il in aktif_iller]
    keyboard.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
    await update.message.reply_text(
        f"Merhaba {update.effective_user.first_name}!\n\nHizmet verdigimiz ili secin:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return IL_SEC

async def il_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "iptal":
        await query.edit_message_text("Iptal edildi.")
        return ConversationHandler.END
    il = query.data.split(":", 1)[1]
    context.user_data["il"] = il
    aktif_ilceler = [ilce for ilce in konumlar.get(il, {}) if ilce_konum_sayisi(il, ilce) > 0]
    if not aktif_ilceler:
        await query.edit_message_text(f"{il} ilinde su an musait bolge yok.")
        return ConversationHandler.END
    keyboard = [[InlineKeyboardButton(f"📌 {ilce}", callback_data=f"ilce:{ilce}")] for ilce in aktif_ilceler]
    keyboard.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_il")])
    keyboard.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
    await query.edit_message_text(f"Il: {il}\n\nBolgenizi secin:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ILCE_SEC

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
        keyboard.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
        await query.edit_message_text("Ili secin:", reply_markup=InlineKeyboardMarkup(keyboard))
        return IL_SEC
    ilce = query.data.split(":", 1)[1]
    il   = context.user_data["il"]
    context.user_data["ilce"] = ilce
    urunler = ilce_urunleri_birlestir(il, ilce)
    if not urunler:
        await query.edit_message_text(f"{ilce} bolgesinde su an urun bulunmuyor.")
        return ConversationHandler.END
    keyboard = [[InlineKeyboardButton(f"🍬 {u['ad']}", callback_data=f"urun:{uid}")] for uid, u in urunler.items()]
    keyboard.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_ilce")])
    keyboard.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
    await query.edit_message_text(f"Il: {il} / Bolge: {ilce}\n\nUrun secin:", reply_markup=InlineKeyboardMarkup(keyboard))
    return URUN_SEC

async def urun_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "iptal":
        await query.edit_message_text("Iptal edildi.")
        return ConversationHandler.END
    if query.data == "geri_ilce":
        il = context.user_data["il"]
        aktif_ilceler = [ilce for ilce in konumlar.get(il, {}) if ilce_konum_sayisi(il, ilce) > 0]
        keyboard = [[InlineKeyboardButton(f"📌 {ilce}", callback_data=f"ilce:{ilce}")] for ilce in aktif_ilceler]
        keyboard.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_il")])
        keyboard.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
        await query.edit_message_text("Bolgenizi secin:", reply_markup=InlineKeyboardMarkup(keyboard))
        return ILCE_SEC
    uid  = query.data.split(":", 1)[1]
    il   = context.user_data["il"]
    ilce = context.user_data["ilce"]
    urunler = ilce_urunleri_birlestir(il, ilce)
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
    keyboard.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
    await query.edit_message_text(
        f"Il: {il} / Bolge: {ilce}\nUrun: {urun['ad']}\n\nMiktar secin:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return GRAM_SEC

async def gram_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "iptal":
        await query.edit_message_text("Iptal edildi.")
        return ConversationHandler.END
    if query.data == "geri_urun":
        il   = context.user_data["il"]
        ilce = context.user_data["ilce"]
        urunler = ilce_urunleri_birlestir(il, ilce)
        keyboard = [[InlineKeyboardButton(f"🍬 {u['ad']}", callback_data=f"urun:{uid}")] for uid, u in urunler.items()]
        keyboard.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_ilce")])
        keyboard.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
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
        f"Siparis Ozeti\n─────────────────\n"
        f"Siparis No : {siparis_no}\n"
        f"Il         : {il}\n"
        f"Bolge      : {ilce}\n"
        f"Urun       : {urun_ad}\n"
        f"Miktar     : {gram}\n"
        f"Fiyat      : {fiyat}\n"
        f"─────────────────\n\n{BANKA_BILGILERI}\n\n"
        f"Odemeyi yaptiktan sonra dekont fotografini gonderin."
    )
    keyboard = [
        [InlineKeyboardButton("Siparisi Onayla", callback_data="onayla")],
        [InlineKeyboardButton("⬅️ Geri",         callback_data="geri_gram")],
        [InlineKeyboardButton("❌ Iptal",         callback_data="iptal")],
    ]
    await query.edit_message_text(ozet, reply_markup=InlineKeyboardMarkup(keyboard))
    return ODEME

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
        urunler = ilce_urunleri_birlestir(il, ilce)
        urun    = urunler.get(uid, {})
        gramlar = urun.get("gramlar", {})
        keyboard = [
            [InlineKeyboardButton(f"{gram}  —  {fiyat}", callback_data=f"gram:{gram}:{fiyat}")]
            for gram, fiyat in gramlar.items()
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_urun")])
        keyboard.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
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
            f"Siparisıniz alindi!\n\nSiparis No: {siparis_no}\n\n"
            f"Havale/EFT islemini gerceklestirip dekontu gonderin.\n\nTesekkurler!"
        )
        return ConversationHandler.END

# ─── DEKONT ─────────────────────────────────────────────────────────────────
async def foto_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id == ADMIN_ID:
        if user_id in admin_islem and admin_islem[user_id].get("adim") == "foto":
            admin_islem[user_id]["foto_id"] = update.message.photo[-1].file_id
            admin_islem[user_id]["adim"]    = "konum"
            await update.message.reply_text("Fotograf kaydedildi!\n\nSimdi konumu gonder:")
        else:
            await update.message.reply_text(f"Fotograf ID:\n{update.message.photo[-1].file_id}")
        return
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
    keyboard = [[InlineKeyboardButton(f"Onayla — {siparis_no}", callback_data=f"admin_onayla:{siparis_no}")]]
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=update.message.photo[-1].file_id,
        caption=(
            f"Yeni Dekont!\n\nSiparis: {siparis_no}\n"
            f"Il/Ilce: {siparis.get('il','?')}/{siparis.get('ilce','?')}\n"
            f"Urun: {siparis.get('urun','?')}\n"
            f"Fiyat: {siparis.get('fiyat','?')}\n\nOnaylamak icin butona bas:"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text(f"Dekontunuz alindi! Siparis No: {siparis_no}")

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
        yeni_konum = {
            "id":         konum_id_olustur(),
            "lat":        lat,
            "lon":        lon,
            "foto_id":    foto_id,
            "kullanildi": False,
            "urunler":    {}
        }
        if il not in konumlar:
            konumlar[il] = {}
        if ilce not in konumlar[il]:
            konumlar[il][ilce] = []
        konumlar[il][ilce].append(yeni_konum)
        kaydet(KONUMLAR_DOSYA, konumlar)
        konum_idx = len(konumlar[il][ilce]) - 1
        admin_islem[user_id] = {
            "adim":      "urun_sec",
            "il":        il,
            "ilce":      ilce,
            "konum_idx": konum_idx
        }
        await goster_urun_havuzu(update, user_id, il, ilce, konum_idx)
        return
    await update.message.reply_text("Konum alindi ama aktif islem yok.")

async def goster_urun_havuzu(update_or_msg, user_id, il, ilce, konum_idx):
    """Ürün havuzunu buton olarak göster."""
    if not urun_havuzu:
        keyboard = [[InlineKeyboardButton("➕ Yeni Urun Olustur", callback_data=f"yeni_urun:{il}:{ilce}:{konum_idx}")]]
        mesaj = "Urun havuzu bos!\nYeni urun olusturun:"
    else:
        keyboard = [
            [InlineKeyboardButton(f"🍬 {ad}", callback_data=f"havuz_sec:{uid}:{il}:{ilce}:{konum_idx}")]
            for uid, ad in urun_havuzu.items()
        ]
        keyboard.append([InlineKeyboardButton("➕ Yeni Urun Ekle", callback_data=f"yeni_urun:{il}:{ilce}:{konum_idx}")])

    konum_no = konum_idx + 1
    mesaj = f"Konum #{konum_no} kaydedildi!\n\nBu konuma hangi urunu eklemek istiyorsun?"

    if hasattr(update_or_msg, 'message'):
        await update_or_msg.message.reply_text(mesaj, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update_or_msg.reply_text(mesaj, reply_markup=InlineKeyboardMarkup(keyboard))

# ─── ADMİN BUTON ────────────────────────────────────────────────────────────
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("Yetkisiz!", show_alert=True)
        return
    await query.answer()
    data = query.data

    # ── Havuzdan ürün seç ──
    if data.startswith("havuz_sec:"):
        parcalar  = data.split(":")
        uid       = parcalar[1]
        il        = parcalar[2]
        ilce      = parcalar[3]
        konum_idx = int(parcalar[4])
        urun_ad   = urun_havuzu.get(uid, "")
        admin_islem[ADMIN_ID] = {
            "adim":      "gram_miktar",
            "il":        il,
            "ilce":      ilce,
            "konum_idx": konum_idx,
            "urun_uid":  uid,
            "urun_ad":   urun_ad,
            "gramlar":   {}
        }
        await query.edit_message_text(f"Urun: {urun_ad}\n\nGram miktarini yaz (örn: 1g, 3.5g, 7g):")

    # ── Yeni ürün oluştur ──
    elif data.startswith("yeni_urun:"):
        parcalar  = data.split(":")
        il        = parcalar[1]
        ilce      = parcalar[2]
        konum_idx = int(parcalar[3])
        admin_islem[ADMIN_ID] = {
            "adim":      "yeni_urun_ad",
            "il":        il,
            "ilce":      ilce,
            "konum_idx": konum_idx,
            "gramlar":   {}
        }
        await query.edit_message_text("Yeni urun adini yaz (örn: Skunk, Crystall):")

    # ── Gram devam ──
    elif data == "admin_gram_ekle":
        admin_islem[ADMIN_ID]["adim"] = "gram_miktar"
        await query.edit_message_text("Yeni gram miktarini yaz:")

    # ── Kaydet ──
    elif data == "admin_kaydet":
        islem     = admin_islem.get(ADMIN_ID, {})
        il        = islem["il"]
        ilce      = islem["ilce"]
        konum_idx = islem["konum_idx"]
        uid       = islem["urun_uid"]
        urun_ad   = islem["urun_ad"]
        gramlar   = islem["gramlar"]
        konumlar[il][ilce][konum_idx]["urunler"][uid] = {"ad": urun_ad, "gramlar": gramlar}
        kaydet(KONUMLAR_DOSYA, konumlar)
        gram_metni = "\n".join([f"  {g}: {f}" for g, f in gramlar.items()])
        keyboard = [
            [InlineKeyboardButton("➕ Bu Konuma Baska Urun Ekle", callback_data=f"konum_urun_ekle:{il}:{ilce}:{konum_idx}")],
            [InlineKeyboardButton("📍 Yeni Konum Ekle",           callback_data=f"yeni_konum_ekle:{il}:{ilce}")],
            [InlineKeyboardButton("✅ Tamamlandi",                 callback_data="admin_tamam")],
        ]
        del admin_islem[ADMIN_ID]
        kalan = ilce_konum_sayisi(il, ilce)
        await query.edit_message_text(
            f"Kaydedildi!\n\nIl: {il} / Ilce: {ilce}\nUrun: {urun_ad}\nGramlar:\n{gram_metni}\n\nBu ilcede {kalan} aktif konum var.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # ── Bu konuma başka ürün ekle ──
    elif data.startswith("konum_urun_ekle:"):
        parcalar  = data.split(":")
        il        = parcalar[1]
        ilce      = parcalar[2]
        konum_idx = int(parcalar[3])
        keyboard = [
            [InlineKeyboardButton(f"🍬 {ad}", callback_data=f"havuz_sec:{uid}:{il}:{ilce}:{konum_idx}")]
            for uid, ad in urun_havuzu.items()
        ]
        keyboard.append([InlineKeyboardButton("➕ Yeni Urun Ekle", callback_data=f"yeni_urun:{il}:{ilce}:{konum_idx}")])
        await query.edit_message_text("Hangi urunu eklemek istiyorsun?", reply_markup=InlineKeyboardMarkup(keyboard))

    # ── Yeni konum ekle (aynı ilçeye) ──
    elif data.startswith("yeni_konum_ekle:"):
        parcalar = data.split(":")
        il   = parcalar[1]
        ilce = parcalar[2]
        admin_islem[ADMIN_ID] = {"adim": "foto", "il": il, "ilce": ilce}
        await query.edit_message_text(f"{il}/{ilce} icin yeni konum ekleniyor.\n\nFotografi gonder:")

    elif data == "admin_tamam":
        await query.edit_message_text("Tamamlandi! /konum_ekle ile yeni konum ekleyebilirsin.")

    # ── Sipariş onayla ──
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
            await query.edit_message_caption(f"{il}/{ilce} bolgesinde musait konum kalmadi!\n/konum_ekle ile ekleyin.")
            return
        aktif_siparisler[siparis_no]["durum"] = "isleniyor"
        kaydet(SIPARISLER_DOSYA, aktif_siparisler)
        musteri_id = siparis["user_id"]
        await context.bot.send_photo(
            chat_id=musteri_id, photo=konum["foto_id"],
            caption=f"Siparisıniz hazirlandi!\n\nSiparis No: {siparis_no}\nAsagidaki konumdan teslim alabilirsiniz."
        )
        await context.bot.send_location(chat_id=musteri_id, latitude=konum["lat"], longitude=konum["lon"])
        await context.bot.send_message(chat_id=musteri_id,
            text=f"Siparisıniz teslimata hazir!\n\nSiparis No: {siparis_no}\n\nIyi gunler!")
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

# ─── ADMİN METİN ────────────────────────────────────────────────────────────
async def metin_isle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    metin   = update.message.text.strip()

    if user_id == ADMIN_ID and user_id in admin_islem:
        islem = admin_islem[user_id]
        adim  = islem.get("adim")

        # Yeni ürün adı
        if adim == "yeni_urun_ad":
            uid = urun_id_olustur()
            urun_havuzu[uid] = metin
            kaydet(URUN_HAVUZU_DOSYA, urun_havuzu)
            admin_islem[user_id].update({
                "adim":     "gram_miktar",
                "urun_uid": uid,
                "urun_ad":  metin,
                "gramlar":  {}
            })
            await update.message.reply_text(f"Urun '{metin}' havuza eklendi!\n\nGram miktarini yaz (örn: 1g):")
            return

        # Gram miktarı
        elif adim == "gram_miktar":
            admin_islem[user_id]["gecici_gram"] = metin
            admin_islem[user_id]["adim"]        = "gram_fiyat"
            await update.message.reply_text(f"{metin} icin fiyati yaz:")
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
                await update.message.reply_text("Gecersiz fiyat! Sayi gir, örn: 150")
            return

        # Yeni ürün adı (havuza ekle)
        elif adim == "yeni_urun_ad":
            uid = urun_id_olustur()
            urun_havuzu[uid] = metin
            kaydet(URUN_HAVUZU_DOSYA, urun_havuzu)
            admin_islem[user_id].update({
                "adim":     "gram_miktar",
                "urun_uid": uid,
                "urun_ad":  metin,
                "gramlar":  {}
            })
            await update.message.reply_text(f"Urun '{metin}' eklendi!\n\nGram miktarini yaz (örn: 1g, 3.5g):")
            return

        # Yeni il
        elif adim == "yeni_il":
            if metin not in konumlar:
                konumlar[metin] = {}
                kaydet(KONUMLAR_DOSYA, konumlar)
            del admin_islem[user_id]
            iller = list(konumlar.keys())
            keyboard = [[InlineKeyboardButton(f"📍 {il}", callback_data=f"kekle_il:{il}")] for il in iller]
            keyboard.append([InlineKeyboardButton("➕ Yeni Il Ekle", callback_data="kekle_yeni_il")])
            await update.message.reply_text(f"'{metin}' eklendi! Ili sec:", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # Yeni ilçe
        elif adim == "yeni_ilce":
            il = islem["il"]
            if il not in konumlar:
                konumlar[il] = {}
            if metin not in konumlar[il]:
                konumlar[il][metin] = []
                kaydet(KONUMLAR_DOSYA, konumlar)
            admin_islem[user_id] = {"adim": "foto", "il": il, "ilce": metin}
            await update.message.reply_text(f"Ilce '{metin}' eklendi!\n\nFotografi gonder:")
            return

    await update.message.reply_text("Siparis vermek icin /start yazin.")

# ─── ADMİN: /konum_ekle ─────────────────────────────────────────────────────
async def konum_ekle_baslat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    iller = list(konumlar.keys())
    keyboard = [[InlineKeyboardButton(f"📍 {il}", callback_data=f"kekle_il:{il}")] for il in iller]
    keyboard.append([InlineKeyboardButton("➕ Yeni Il Ekle", callback_data="kekle_yeni_il")])
    await update.message.reply_text("Konum eklenecek ili sec:", reply_markup=InlineKeyboardMarkup(keyboard))

async def konum_ekle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("Yetkisiz!", show_alert=True)
        return
    await query.answer()
    data = query.data

    if data == "kekle_yeni_il":
        admin_islem[ADMIN_ID] = {"adim": "yeni_il"}
        await query.edit_message_text("Yeni ilin adini yaz:")

    elif data.startswith("kekle_il:"):
        il     = data.split(":", 1)[1]
        ilceler = list(konumlar.get(il, {}).keys())
        keyboard = [[InlineKeyboardButton(f"📌 {ilce}", callback_data=f"kekle_ilce:{il}:{ilce}")] for ilce in ilceler]
        keyboard.append([InlineKeyboardButton("➕ Yeni Ilce Ekle", callback_data=f"kekle_yeni_ilce:{il}")])
        await query.edit_message_text(f"Il: {il}\n\nIlce sec:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("kekle_yeni_ilce:"):
        il = data.split(":", 1)[1]
        admin_islem[ADMIN_ID] = {"adim": "yeni_ilce", "il": il}
        await query.edit_message_text(f"{il} icin yeni ilce adini yaz:")

    elif data.startswith("kekle_ilce:"):
        parcalar = data.split(":")
        il   = parcalar[1]
        ilce = parcalar[2]
        admin_islem[ADMIN_ID] = {"adim": "foto", "il": il, "ilce": ilce}
        await query.edit_message_text(f"Il: {il} / Ilce: {ilce}\n\nFotografi gonder:")

# ─── ADMİN: /urunler (havuz yönetimi) ───────────────────────────────────────
async def urun_havuzu_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not urun_havuzu:
        keyboard = [[InlineKeyboardButton("➕ Urun Ekle", callback_data="havuz_yeni_urun")]]
        await update.message.reply_text("Urun havuzu bos.", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    keyboard = [
        [InlineKeyboardButton(f"🍬 {ad}  🗑", callback_data=f"havuz_sil:{uid}")]
        for uid, ad in urun_havuzu.items()
    ]
    keyboard.append([InlineKeyboardButton("➕ Yeni Urun Ekle", callback_data="havuz_yeni_urun")])
    await update.message.reply_text("Urun Havuzu\n─────────────────\nSilmek icin urunun uzerine tikla:",
                                     reply_markup=InlineKeyboardMarkup(keyboard))

async def urun_havuzu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("Yetkisiz!", show_alert=True)
        return
    await query.answer()
    data = query.data

    if data == "havuz_yeni_urun":
        admin_islem[ADMIN_ID] = {"adim": "havuz_urun_ad"}
        await query.edit_message_text("Yeni urun adini yaz:")

    elif data.startswith("havuz_sil:"):
        uid = data.split(":")[1]
        ad  = urun_havuzu.pop(uid, "")
        kaydet(URUN_HAVUZU_DOSYA, urun_havuzu)
        keyboard = [
            [InlineKeyboardButton(f"🍬 {a}  🗑", callback_data=f"havuz_sil:{u}")]
            for u, a in urun_havuzu.items()
        ]
        keyboard.append([InlineKeyboardButton("➕ Yeni Urun Ekle", callback_data="havuz_yeni_urun")])
        await query.edit_message_text(
            f"'{ad}' silindi!\n\nUrun Havuzu:",
            reply_markup=InlineKeyboardMarkup(keyboard) if urun_havuzu else None
        )

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
    app.add_handler(CommandHandler("urunler",    urun_havuzu_goster))

    app.add_handler(CallbackQueryHandler(admin_callback,       pattern=r"^(admin_onayla:|admin_gram_ekle|admin_kaydet|admin_tamam|havuz_sec:|yeni_urun:|konum_urun_ekle:|yeni_konum_ekle:)"))
    app.add_handler(CallbackQueryHandler(konum_ekle_callback,  pattern=r"^(kekle_)"))
    app.add_handler(CallbackQueryHandler(urun_havuzu_callback, pattern=r"^(havuz_sil:|havuz_yeni_urun)"))

    app.add_handler(MessageHandler(filters.PHOTO,    foto_al))
    app.add_handler(MessageHandler(filters.LOCATION, konum_al))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, metin_isle))

    logger.info(f"Bot basladi. Siparis: {len(aktif_siparisler)} | Urun havuzu: {len(urun_havuzu)}")
    app.run_polling()

if __name__ == "__main__":
    main()
