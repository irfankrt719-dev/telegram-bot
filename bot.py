"""
Telegram Sipariş Botu - Gram Bazlı Fiyatlandırma
=================================================
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
🏦 Ödeme Bilgileri

Banka: Ziraat Bankası
Hesap Adı: Şirket Adı
IBAN: TR00 0000 0000 0000 0000 0000 00

Açıklama kısmına sipariş numaranızı yazmayı unutmayın!
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

URUN_SEC, GRAM_SEC, BOLGE_SEC, ODEME = range(4)

admin_islem  = {}
konum_ekleme = {}

# ─── DOSYALAR ───────────────────────────────────────────────────────────────
SIPARISLER_DOSYA = "siparisler.json"
KONUMLAR_DOSYA   = "konumlar.json"
URUNLER_DOSYA    = "urunler.json"

VARSAYILAN_URUNLER = {
    "urun_1": {
        "ad": "Ürün 1",
        "gramlar": {
            "100g": 50.0,
            "250g": 110.0,
            "500g": 200.0
        }
    }
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

# ─── YARDIMCI FONKSİYONLAR ──────────────────────────────────────────────────
def bolge_icin_konum_sec(bolge_adi):
    for k in konumlar.get(bolge_adi, []):
        if not k.get("kullanildi") and k.get("foto_id"):
            return k
    return None

def konumu_kullanildi_isaretle(bolge_adi, konum_id):
    for k in konumlar.get(bolge_adi, []):
        if k["id"] == konum_id:
            k["kullanildi"] = True
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
        await update.message.reply_text("Şu an ürün bulunmuyor. Lütfen daha sonra deneyin.")
        return ConversationHandler.END
    keyboard = [
        [InlineKeyboardButton(f"🍬 {v['ad']}", callback_data=k)]
        for k, v in urunler.items()
    ]
    keyboard.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])
    await update.message.reply_text(
        f"👋 Merhaba *{update.effective_user.first_name}*!\n\nLütfen bir ürün seçin:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
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
        await query.edit_message_text("Geçersiz seçim.")
        return ConversationHandler.END

    context.user_data["urun_kodu"] = query.data
    context.user_data["urun_ad"]   = urun["ad"]

    gramlar = urun.get("gramlar", {})
    keyboard = [
        [InlineKeyboardButton(f"{gram}  —  {fiyat}", callback_data=f"gram:{gram}:{fiyat}")]
        for gram, fiyat in gramlar.items()
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_urun")])
    keyboard.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])

    await query.edit_message_text(
        f"🍬 *{urun['ad']}*\n\nMiktar seçin:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return GRAM_SEC

async def gram_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "iptal":
        await query.edit_message_text("❌ İptal edildi.")
        return ConversationHandler.END

    if query.data == "geri_urun":
        keyboard = [
            [InlineKeyboardButton(f"🍬 {v['ad']}", callback_data=k)]
            for k, v in urunler.items()
        ]
        keyboard.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])
        await query.edit_message_text("Lütfen bir ürün seçin:", parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup(keyboard))
        return URUN_SEC

    # gram:100g:50.0
    parcalar = query.data.split(":")
    gram     = parcalar[1]
    fiyat    = float(parcalar[2])

    context.user_data["gram"]       = gram
    context.user_data["urun_fiyat"] = fiyat

    keyboard = [
        [InlineKeyboardButton(f"📌 {ad}", callback_data=kod)]
        for kod, ad in BOLGELER.items()
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_gram")])
    keyboard.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])

    await query.edit_message_text(
        f"🍬 *{context.user_data['urun_ad']}* — {gram}\nFiyat: {fiyat}\n\n📍 Bölgenizi seçin:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return BOLGE_SEC

async def bolge_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "iptal":
        await query.edit_message_text("❌ İptal edildi.")
        return ConversationHandler.END

    if query.data == "geri_gram":
        urun = urunler.get(context.user_data.get("urun_kodu"), {})
        gramlar = urun.get("gramlar", {})
        keyboard = [
            [InlineKeyboardButton(f"{gram}  —  {fiyat}", callback_data=f"gram:{gram}:{fiyat}")]
            for gram, fiyat in gramlar.items()
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_urun")])
        keyboard.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])
        await query.edit_message_text(
            f"🍬 *{urun.get('ad','')}*\n\nMiktar seçin:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return GRAM_SEC

    bolge_ad = BOLGELER.get(query.data)
    if not bolge_ad:
        await query.edit_message_text("Geçersiz bölge.")
        return ConversationHandler.END

    siparis_no = siparis_no_olustur(update.effective_user.id)
    context.user_data.update({"bolge": bolge_ad, "siparis_no": siparis_no})

    urun_ad = context.user_data["urun_ad"]
    gram    = context.user_data["gram"]
    fiyat   = context.user_data["urun_fiyat"]

    ozet = (
        f"📋 Sipariş Özeti\n"
        f"─────────────────\n"
        f"Sipariş No : {siparis_no}\n"
        f"Ürün       : {urun_ad}\n"
        f"Miktar     : {gram}\n"
        f"Bölge      : {bolge_ad}\n"
        f"Fiyat      : {fiyat}\n"
        f"─────────────────\n\n"
        f"{BANKA_BILGILERI}\n\n"
        f"Ödemeyi yaptıktan sonra dekont fotoğrafını gönderin."
    )

    keyboard = [
        [InlineKeyboardButton("✅ Siparişi Onayla", callback_data="onayla")],
        [InlineKeyboardButton("⬅️ Geri",            callback_data="geri_bolge")],
        [InlineKeyboardButton("❌ İptal",            callback_data="iptal")],
    ]
    await query.edit_message_text(ozet, reply_markup=InlineKeyboardMarkup(keyboard))
    return ODEME

async def odeme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "iptal":
        await query.edit_message_text("❌ İptal edildi.")
        return ConversationHandler.END

    if query.data == "geri_bolge":
        keyboard = [
            [InlineKeyboardButton(f"📌 {ad}", callback_data=kod)]
            for kod, ad in BOLGELER.items()
        ]
        keyboard.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])
        await query.edit_message_text("📍 Bölgenizi seçin:",
                                      reply_markup=InlineKeyboardMarkup(keyboard))
        return BOLGE_SEC

    if query.data == "onayla":
        siparis_no = context.user_data.get("siparis_no", "?")
        aktif_siparisler[siparis_no] = {
            "user_id": update.effective_user.id,
            "urun":    f"{context.user_data.get('urun_ad')} {context.user_data.get('gram')}",
            "bolge":   context.user_data.get("bolge"),
            "fiyat":   context.user_data.get("urun_fiyat"),
            "durum":   "beklemede"
        }
        kaydet(SIPARISLER_DOSYA, aktif_siparisler)
        await query.edit_message_text(
            f"Siparişiniz alındı!\n\n"
            f"Sipariş No: {siparis_no}\n\n"
            f"Havale/EFT işlemini gerçekleştirip dekontu gönderin.\n\nTeşekkürler!"
        )
        return ConversationHandler.END

# ─── ÜRÜN YÖNETİMİ ──────────────────────────────────────────────────────────
async def urun_yonetim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await urun_listesi_goster(update, context)

async def urun_listesi_goster(update_or_query, context, guncelle=False):
    keyboard = []
    for kid, u in urunler.items():
        gram_sayisi = len(u.get("gramlar", {}))
        keyboard.append([InlineKeyboardButton(
            f"🍬 {u['ad']} ({gram_sayisi} miktar)",
            callback_data=f"urun_detay:{kid}"
        )])
    keyboard.append([InlineKeyboardButton("➕ Yeni Ürün Ekle", callback_data="urun_ekle")])

    mesaj = "Urun Yonetimi\n─────────────────\nBir ürüne tıklayarak düzenle veya sil."

    if guncelle and hasattr(update_or_query, 'edit_message_text'):
        await update_or_query.edit_message_text(mesaj, reply_markup=InlineKeyboardMarkup(keyboard))
    elif hasattr(update_or_query, 'message'):
        await update_or_query.message.reply_text(mesaj, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update_or_query.reply_text(mesaj, reply_markup=InlineKeyboardMarkup(keyboard))

async def urun_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("Yetkisiz!", show_alert=True)
        return
    await query.answer()
    data = query.data

    if data.startswith("urun_detay:"):
        kid = data.split(":")[1]
        u   = urunler.get(kid)
        if not u:
            await query.edit_message_text("Urun bulunamadi.")
            return
        gramlar = u.get("gramlar", {})
        gram_metni = "\n".join([f"  {g}: {f}" for g, f in gramlar.items()])
        keyboard = [
            [InlineKeyboardButton("➕ Gram Ekle",    callback_data=f"gram_ekle:{kid}")],
            [InlineKeyboardButton("➖ Gram Sil",     callback_data=f"gram_sil_sec:{kid}")],
            [InlineKeyboardButton("✏️ Adı Değiştir", callback_data=f"urun_ad:{kid}")],
            [InlineKeyboardButton("🗑 Ürünü Sil",    callback_data=f"urun_sil:{kid}")],
            [InlineKeyboardButton("⬅️ Geri",         callback_data="urun_geri")],
        ]
        await query.edit_message_text(
            f"🍬 {u['ad']}\n\nMiktarlar:\n{gram_metni}\n\nNe yapmak istiyorsun?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "urun_geri":
        await urun_listesi_goster(query, context, guncelle=True)

    elif data == "urun_ekle":
        admin_islem[ADMIN_ID] = {"islem": "urun_ekle_ad"}
        await query.edit_message_text("Yeni Urun Ekleniyor\n\nUrünün adını yaz:")

    elif data.startswith("urun_ad:"):
        kid = data.split(":")[1]
        admin_islem[ADMIN_ID] = {"islem": "urun_ad_guncelle", "kid": kid}
        u = urunler.get(kid, {})
        await query.edit_message_text(f"{u.get('ad','')} icin yeni adi yaz:")

    elif data.startswith("urun_sil:"):
        kid = data.split(":")[1]
        u   = urunler.pop(kid, None)
        if u:
            kaydet(URUNLER_DOSYA, urunler)
            await query.edit_message_text(f"{u['ad']} silindi!")
            await urun_listesi_goster(query, context, guncelle=False)

    elif data.startswith("gram_ekle:"):
        kid = data.split(":")[1]
        admin_islem[ADMIN_ID] = {"islem": "gram_ekle_miktar", "kid": kid}
        await query.edit_message_text(
            f"Gram Ekleniyor\n\nMiktari yaz (örn: 250g, 1kg):"
        )

    elif data.startswith("gram_sil_sec:"):
        kid     = data.split(":")[1]
        u       = urunler.get(kid, {})
        gramlar = u.get("gramlar", {})
        if not gramlar:
            await query.edit_message_text("Silinecek miktar yok.")
            return
        keyboard = [
            [InlineKeyboardButton(f"🗑 {g} — {f}", callback_data=f"gram_sil:{kid}:{g}")]
            for g, f in gramlar.items()
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Geri", callback_data=f"urun_detay:{kid}")])
        await query.edit_message_text("Hangi miktarı silmek istiyorsun?",
                                      reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("gram_sil:"):
        parcalar = data.split(":")
        kid  = parcalar[1]
        gram = parcalar[2]
        if kid in urunler and gram in urunler[kid].get("gramlar", {}):
            del urunler[kid]["gramlar"][gram]
            kaydet(URUNLER_DOSYA, urunler)
            await query.edit_message_text(f"{gram} silindi!")
            await urun_listesi_goster(query, context, guncelle=False)

# ─── ADMIN METİN İŞLE ───────────────────────────────────────────────────────
async def admin_metin_isle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    metin   = update.message.text.strip()

    if user_id == ADMIN_ID and user_id in admin_islem:
        islem = admin_islem[user_id]

        if islem["islem"] == "urun_ekle_ad":
            admin_islem[user_id] = {"islem": "urun_ekle_gram_mi", "ad": metin}
            keyboard = [
                [InlineKeyboardButton("➕ Gram Ekle", callback_data="yeni_gram_ekle")],
                [InlineKeyboardButton("✅ Bitti",      callback_data="gram_bitti")],
            ]
            admin_islem[user_id] = {"islem": "urun_ekle_gram_bekle", "ad": metin, "gramlar": {}}
            await update.message.reply_text(
                f"Ad: {metin}\n\nŞimdi gram miktarı yaz (örn: 250g):",
            )
            admin_islem[user_id]["islem"] = "urun_ekle_gram_miktar"
            return

        elif islem["islem"] == "urun_ekle_gram_miktar":
            admin_islem[user_id]["gecici_gram"] = metin
            admin_islem[user_id]["islem"]       = "urun_ekle_gram_fiyat"
            await update.message.reply_text(f"{metin} için fiyatı yaz (örn: 85):")
            return

        elif islem["islem"] == "urun_ekle_gram_fiyat":
            try:
                fiyat = float(metin.replace(",", "."))
                gram  = admin_islem[user_id]["gecici_gram"]
                admin_islem[user_id]["gramlar"][gram] = fiyat
                admin_islem[user_id]["islem"] = "urun_ekle_gram_devam"
                keyboard = [
                    [InlineKeyboardButton("➕ Başka Gram Ekle", callback_data="devam_gram")],
                    [InlineKeyboardButton("✅ Kaydet",           callback_data="gram_kaydet")],
                ]
                gramlar = admin_islem[user_id]["gramlar"]
                gram_metni = "\n".join([f"  {g}: {f}" for g, f in gramlar.items()])
                await update.message.reply_text(
                    f"Eklendi!\n\nMevcut miktarlar:\n{gram_metni}",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except ValueError:
                await update.message.reply_text("Gecersiz fiyat! Sadece sayı gir, örn: 85")
            return

        elif islem["islem"] == "gram_ekle_miktar":
            admin_islem[user_id]["gecici_gram"] = metin
            admin_islem[user_id]["islem"]       = "gram_ekle_fiyat"
            await update.message.reply_text(f"{metin} icin fiyati yaz:")
            return

        elif islem["islem"] == "gram_ekle_fiyat":
            try:
                fiyat = float(metin.replace(",", "."))
                gram  = admin_islem[user_id]["gecici_gram"]
                kid   = admin_islem[user_id]["kid"]
                if kid in urunler:
                    if "gramlar" not in urunler[kid]:
                        urunler[kid]["gramlar"] = {}
                    urunler[kid]["gramlar"][gram] = fiyat
                    kaydet(URUNLER_DOSYA, urunler)
                del admin_islem[user_id]
                await update.message.reply_text(f"{gram} — {fiyat} eklendi!")
                await urun_listesi_goster(update, context)
            except ValueError:
                await update.message.reply_text("Gecersiz fiyat!")
            return

        elif islem["islem"] == "urun_ad_guncelle":
            kid = islem["kid"]
            if kid in urunler:
                eski = urunler[kid]["ad"]
                urunler[kid]["ad"] = metin
                kaydet(URUNLER_DOSYA, urunler)
                del admin_islem[user_id]
                await update.message.reply_text(f"{eski} → {metin} guncellendi!")
                await urun_listesi_goster(update, context)
            return

    await update.message.reply_text("Sipariş vermek için /start yazın.")

async def urun_gram_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("Yetkisiz!", show_alert=True)
        return
    await query.answer()

    if query.data == "devam_gram":
        admin_islem[ADMIN_ID]["islem"] = "urun_ekle_gram_miktar"
        await query.edit_message_text("Yeni gram miktarı yaz (örn: 500g):")

    elif query.data == "gram_kaydet":
        islem = admin_islem.get(ADMIN_ID, {})
        ad      = islem.get("ad", "")
        gramlar = islem.get("gramlar", {})
        kid     = urun_id_olustur()
        urunler[kid] = {"ad": ad, "gramlar": gramlar}
        kaydet(URUNLER_DOSYA, urunler)
        del admin_islem[ADMIN_ID]
        gram_metni = "\n".join([f"  {g}: {f}" for g, f in gramlar.items()])
        await query.edit_message_text(f"{ad} eklendi!\n\nMiktarlar:\n{gram_metni}")
        await urun_listesi_goster(query, context, guncelle=False)

# ─── DEKONT GELDİĞİNDE ──────────────────────────────────────────────────────
async def foto_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id == ADMIN_ID:
        if user_id in konum_ekleme and konum_ekleme[user_id]["adim"] == "foto":
            konum_ekleme[user_id]["foto_id"] = update.message.photo[-1].file_id
            konum_ekleme[user_id]["adim"]    = "konum"
            bolge = konum_ekleme[user_id]["bolge"]
            await update.message.reply_text(f"{bolge} icin konumu gonder:")
        else:
            foto_id = update.message.photo[-1].file_id
            await update.message.reply_text(f"Fotograf ID:\n{foto_id}")
        return

    siparis_no = context.user_data.get("siparis_no")
    if not siparis_no:
        for no, s in aktif_siparisler.items():
            if str(s["user_id"]) == str(user_id) and s["durum"] == "beklemede":
                siparis_no = no
                break

    if not siparis_no:
        await update.message.reply_text("Aktif siparisıniz yok. /start ile baslayın.")
        return

    siparis  = aktif_siparisler.get(siparis_no, {})
    keyboard = [[InlineKeyboardButton(f"Onayla — {siparis_no}",
                                      callback_data=f"admin_onayla:{siparis_no}")]]
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=update.message.photo[-1].file_id,
        caption=(
            f"Yeni Dekont!\n\n"
            f"Siparis No: {siparis_no}\n"
            f"Urun: {siparis.get('urun','?')}\n"
            f"Bolge: {siparis.get('bolge','?')}\n"
            f"Fiyat: {siparis.get('fiyat','?')}\n\n"
            f"Onaylamak icin butona bas:"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text(
        f"Dekontunuz alındı! Sipariş No: {siparis_no}\nEn kısa sürede onay gönderilecektir."
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
            f"{bolge} bolgesine konum eklendi!\nKullanilabilir konum: {kalan}"
        )
        return
    await update.message.reply_text("Konum alındı ama aktif işlem yok.")

# ─── ADMİN BUTON: Sipariş Onayla ────────────────────────────────────────────
async def admin_buton_onayla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("Yetkisiz!", show_alert=True)
        return
    await query.answer()
    siparis_no = query.data.split(":")[1]
    siparis    = aktif_siparisler.get(siparis_no)
    if not siparis:
        await query.edit_message_caption(f"{siparis_no} bulunamadi.")
        return
    if siparis["durum"] in ("isleniyor", "tamamlandi"):
        await query.answer(f"Bu siparis zaten {siparis['durum']}!", show_alert=True)
        return
    bolge = siparis["bolge"]
    konum = bolge_icin_konum_sec(bolge)
    if not konum:
        await query.edit_message_caption(f"{bolge} bolgesinde konum kalmadi! /konum_ekle ile ekleyin.")
        return
    aktif_siparisler[siparis_no]["durum"] = "isleniyor"
    kaydet(SIPARISLER_DOSYA, aktif_siparisler)
    musteri_id = siparis["user_id"]
    await context.bot.send_photo(
        chat_id=musteri_id, photo=konum["foto_id"],
        caption=f"Siparisıniz hazırlandi!\n\nSiparis No: {siparis_no}\nAsagidaki konumdan teslim alabilirsiniz."
    )
    await context.bot.send_location(chat_id=musteri_id, latitude=konum["lat"], longitude=konum["lon"])
    await context.bot.send_message(
        chat_id=musteri_id,
        text=f"Siparisıniz teslimata hazır!\n\nSiparis No: {siparis_no}\n\nIyi gunler!"
    )
    konumu_kullanildi_isaretle(bolge, konum["id"])
    aktif_siparisler[siparis_no]["durum"] = "tamamlandi"
    kaydet(SIPARISLER_DOSYA, aktif_siparisler)
    kalan = bolge_konum_sayisi(bolge)
    uyari = f"\n\n{bolge} bolgesinde {kalan} konum kaldi!" if kalan <= 3 else ""
    await query.edit_message_caption(f"Tamamlandi! {siparis_no}{uyari}")

# ─── ADMİN: /konum_ekle ─────────────────────────────────────────────────────
async def konum_ekle_baslat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    keyboard = [
        [InlineKeyboardButton(f"📌 {ad}", callback_data=f"konum_ekle_bolge:{ad}")]
        for ad in BOLGELER.values()
    ]
    await update.message.reply_text("Hangi bolgeye konum eklemek istiyorsun?",
                                     reply_markup=InlineKeyboardMarkup(keyboard))

async def konum_ekle_bolge_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("Yetkisiz!", show_alert=True)
        return
    await query.answer()
    bolge = query.data.split(":")[1]
    konum_ekleme[ADMIN_ID] = {"adim": "foto", "bolge": bolge, "foto_id": None}
    await query.edit_message_text(f"{bolge} bolgesine konum ekleniyor\n\nAdim 1: Fotografi gonder")

# ─── ADMİN: /konumlar ───────────────────────────────────────────────────────
async def konumlar_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    mesaj = "Bolge Konum Durumu\n─────────────────\n"
    for bolge in BOLGELER.values():
        liste = konumlar.get(bolge, [])
        kalan = sum(1 for k in liste if not k.get("kullanildi") and k.get("foto_id"))
        emoji = "🟢" if kalan > 3 else ("🟡" if kalan > 0 else "🔴")
        mesaj += f"\n{emoji} {bolge}: {kalan} kullanilabilir / {len(liste)} toplam\n"
    mesaj += "\n/konum_ekle ile yeni konum ekleyebilirsin."
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
        mesaj += f"\n{emoji} {no} — {s['urun']} | {s['bolge']} | {s['fiyat']}\n"
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
            URUN_SEC:  [CallbackQueryHandler(urun_sec)],
            GRAM_SEC:  [CallbackQueryHandler(gram_sec)],
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
    app.add_handler(CallbackQueryHandler(urun_callback,        pattern=r"^(urun_|gram_)"))
    app.add_handler(CallbackQueryHandler(urun_gram_callback,   pattern=r"^(devam_gram|gram_kaydet)$"))
    app.add_handler(MessageHandler(filters.PHOTO,    foto_al))
    app.add_handler(MessageHandler(filters.LOCATION, konum_al))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_metin_isle))
    logger.info(f"Bot basladi. Urun: {len(urunler)} | Siparis: {len(aktif_siparisler)}")
    app.run_polling()

if __name__ == "__main__":
    main()
