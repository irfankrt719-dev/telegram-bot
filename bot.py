"""
Telegram Sipariş Botu
=====================
- Fiyatlar ürün+gramaja bağlı (konuma değil)
- Konum eklerken sadece foto+konum+ürün+gramaj seç
- Her konum: 1 foto + 1 koordinat + 1 ürün + 1 gramaj
"""

import logging, json, os, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters, ConversationHandler
)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "BURAYA_TOKEN")
ADMIN_ID  = int(os.environ.get("ADMIN_ID", "123456789"))

BANKA = (
    "Odeme Bilgileri\n"
    "─────────────────\n"
    "Banka: Ziraat Bankasi\n"
    "Hesap Adi: Sirket Adi\n"
    "IBAN: TR00 0000 0000 0000 0000 0000 00\n\n"
    "Aciklama kismina siparis numaranizi yazin!"
)

IL, ILCE, URUN, GRAM, ODEME_SEC, ODEME = range(6)
adm = {}

S_DOSYA = "siparisler.json"
K_DOSYA = "konumlar.json"
H_DOSYA = "havuz.json"
O_DOSYA = "odeme.json"
M_DOSYA = "musteriler.json"

# Indirim ayarlari
INDIRIM_HER_N_SIPARIS = 5   # Her 5 sipariste bir indirim
INDIRIM_ORANI         = 10  # %10 indirim

# Havuz yapısı: { hid: { "ad": "Skunk", "miktarlar": { "1g": 150, "3.5g": 450 } } }
HAVUZ_VARSAYILAN = {
    "h1": {"ad": "Deneme 1", "tip": "gram",  "miktarlar": {"2.5": {"tl": 4000.0, "usd": 80.0}, "5": {"tl": 7000.0, "usd": 150.0}}},
    "h2": {"ad": "Deneme 2", "tip": "tekli", "miktarlar": {"Jilet": {"tl": 2000.0, "usd": 40.0}, "Kutu": {"tl": 7000.0, "usd": 150.0}}}
}

ODEME_VARSAYILAN = {
    "iban":  "Odeme Yontemi: IBAN / Havale\n─────────────────\nBanka: Ziraat Bankasi\nHesap Adi: Sirket Adi\nIBAN: TR00 0000 0000 0000 0000 0000 00\n\nAciklama kismina siparis numaranizi yazin!",
    "trc20": "Odeme Yontemi: TRC20 (USDT)\n─────────────────\nAdres: BURAYA_TRC20_ADRESINIZI_YAZIN\n\nGondermeden once adresi kontrol edin!"
}

def yukle(d, v):
    if os.path.exists(d):
        try:
            with open(d, encoding="utf-8") as f:
                return json.load(f)
        except:
            return v
    return v

def kaydet(d, data):
    with open(d, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

siparisler      = yukle(S_DOSYA, {})
konumlar        = yukle(K_DOSYA, {})
havuz           = yukle(H_DOSYA, HAVUZ_VARSAYILAN)
odeme_bilgileri = yukle(O_DOSYA, ODEME_VARSAYILAN)
musteriler      = yukle(M_DOSYA, {})
# musteriler yapisi: { "user_id": { "tamamlanan": 5, "ad": "Ali" } }

if not os.path.exists(H_DOSYA):
    kaydet(H_DOSYA, havuz)
if not os.path.exists(O_DOSYA):
    kaydet(O_DOSYA, odeme_bilgileri)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── YARDIMCI ────────────────────────────────────────────────────────────────
def sp_no(uid):
    return f"SP{uid%10000:04d}{int(time.time())%10000:04d}"

def k_id():
    return f"k{int(time.time())}"

def fiyat_str(f):
    try:
        f = float(f)
        return str(int(f)) if f == int(f) else str(f)
    except:
        return str(f)

def miktar_fiyat_str(fiyat_obj):
    """{ tl: 150, usd: 5 } veya eski format sayı -> string döner"""
    if isinstance(fiyat_obj, dict):
        tl  = fiyat_obj.get("tl", 0)
        usd = fiyat_obj.get("usd", 0)
        return f"{fiyat_str(tl)}₺ / {fiyat_str(usd)}$"
    return fiyat_str(fiyat_obj)

def miktar_tl(fiyat_obj):
    if isinstance(fiyat_obj, dict):
        return float(fiyat_obj.get("tl", 0))
    return float(fiyat_obj)

def miktar_usd(fiyat_obj):
    if isinstance(fiyat_obj, dict):
        return float(fiyat_obj.get("usd", 0))
    return float(fiyat_obj)

def havuz_ad(hid):
    u = havuz.get(hid, {})
    return u["ad"] if isinstance(u, dict) else str(u)

def havuz_miktarlar(hid):
    """{ miktar: fiyat } döner"""
    u = havuz.get(hid, {})
    if isinstance(u, dict):
        return u.get("miktarlar", {})
    return {}

def havuz_tip(hid):
    u = havuz.get(hid, {})
    return u.get("tip", "gram") if isinstance(u, dict) else "gram"

def tip_label(tip):
    return {"gram": "Gram", "tekli": "Tekli (Adet)", "kutu": "Kutu"}.get(tip, tip)

def ilce_aktif_konumlar(il, ilce):
    return [k for k in konumlar.get(il, {}).get(ilce, [])
            if not k.get("silindi") and k.get("foto_id") and k.get("urun")]

def ilce_urunler(il, ilce):
    """İlçedeki aktif konumların ürünlerini topla. { urun_ad: {gram: {tl,usd} } }"""
    sonuc = {}
    for k in ilce_aktif_konumlar(il, ilce):
        u   = k.get("urun", {})
        ad  = u.get("ad", "?")
        g   = str(u.get("gram", "?"))
        # Fiyat eski format (sayı) veya yeni format (dict)
        raw_fiyat = u.get("fiyat", 0)
        if isinstance(raw_fiyat, dict):
            f = raw_fiyat
        else:
            f = {"tl": float(raw_fiyat), "usd": 0}
        if ad not in sonuc:
            sonuc[ad] = {}
        sonuc[ad][g] = f
    return sonuc

def ilce_konum_bul(il, ilce, urun_ad, gram):
    for k in konumlar.get(il, {}).get(ilce, []):
        if k.get("silindi"):
            continue
        u = k.get("urun", {})
        if u.get("ad") == urun_ad and str(u.get("gram")) == str(gram):
            return k
    return None

def ilce_konum_sayisi(il, ilce):
    return len(ilce_aktif_konumlar(il, ilce))


# ─── MÜŞTERİ TAKIP ───────────────────────────────────────────────────────────
def musteri_tamamlanan(user_id):
    return musteriler.get(str(user_id), {}).get("tamamlanan", 0)

def musteri_indirim_var_mi(user_id):
    t = musteri_tamamlanan(user_id)
    return t > 0 and t % INDIRIM_HER_N_SIPARIS == 0

def musteri_kalan_siparis(user_id):
    t = musteri_tamamlanan(user_id)
    kalan = INDIRIM_HER_N_SIPARIS - (t % INDIRIM_HER_N_SIPARIS)
    return kalan if kalan != INDIRIM_HER_N_SIPARIS else 0

def indirimli_fiyat(fiyat, user_id):
    if musteri_indirim_var_mi(user_id):
        return round(fiyat * (1 - INDIRIM_ORANI / 100), 2)
    return fiyat

def musteri_guncelle(user_id, ad=""):
    uid = str(user_id)
    if uid not in musteriler:
        musteriler[uid] = {"tamamlanan": 0, "ad": ad}
    if ad and not musteriler[uid].get("ad"):
        musteriler[uid]["ad"] = ad
    musteriler[uid]["tamamlanan"] += 1
    kaydet(M_DOSYA, musteriler)

# ─── MÜŞTERİ AKIŞI ───────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    aktif = [il for il, ilceler in konumlar.items()
             if any(ilce_konum_sayisi(il, ilce) > 0 for ilce in ilceler)]
    if not aktif:
        await update.message.reply_text("Su an hizmet verilen bolge yok.\nLutfen daha sonra tekrar deneyin.")
        return ConversationHandler.END
    kb = [[InlineKeyboardButton(f"📍 {il}", callback_data=f"il:{il}")] for il in aktif]
    kb.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
    await update.message.reply_text(
        f"Merhaba {update.effective_user.first_name}!\n\nIl secin:",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    return IL

async def il_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "iptal":
        await q.edit_message_text("Iptal edildi.")
        return ConversationHandler.END
    il = q.data.split(":", 1)[1]
    context.user_data["il"] = il
    aktif_ilceler = [ilce for ilce in konumlar.get(il, {}) if ilce_konum_sayisi(il, ilce) > 0]
    if not aktif_ilceler:
        await q.edit_message_text(f"{il} ilinde aktif bolge yok.")
        return ConversationHandler.END
    kb = [[InlineKeyboardButton(f"📌 {ilce}", callback_data=f"ilce:{ilce}")] for ilce in aktif_ilceler]
    kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_il")])
    kb.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
    await q.edit_message_text(f"Il: {il}\n\nBolge secin:", reply_markup=InlineKeyboardMarkup(kb))
    return ILCE

async def ilce_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "iptal":
        await q.edit_message_text("Iptal edildi.")
        return ConversationHandler.END
    if q.data == "geri_il":
        aktif = [il for il, ilceler in konumlar.items()
                 if any(ilce_konum_sayisi(il, ilce) > 0 for ilce in ilceler)]
        kb = [[InlineKeyboardButton(f"📍 {il}", callback_data=f"il:{il}")] for il in aktif]
        kb.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
        await q.edit_message_text("Il secin:", reply_markup=InlineKeyboardMarkup(kb))
        return IL
    ilce = q.data.split(":", 1)[1]
    il   = context.user_data["il"]
    context.user_data["ilce"] = ilce
    urunler = ilce_urunler(il, ilce)
    if not urunler:
        await q.edit_message_text(f"{ilce} bolgesinde urun bulunamadi.")
        return ConversationHandler.END
    kb = [[InlineKeyboardButton(f"{ad}", callback_data=f"urun:{ad}")] for ad in urunler.keys()]
    kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_il")])
    kb.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
    await q.edit_message_text(f"Il: {il}  |  Bolge: {ilce}\n\nUrun secin:", reply_markup=InlineKeyboardMarkup(kb))
    return URUN

async def urun_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "iptal":
        await q.edit_message_text("Iptal edildi.")
        return ConversationHandler.END
    if q.data == "geri_il":
        il = context.user_data["il"]
        aktif_ilceler = [ilce for ilce in konumlar.get(il, {}) if ilce_konum_sayisi(il, ilce) > 0]
        kb = [[InlineKeyboardButton(f"📌 {ilce}", callback_data=f"ilce:{ilce}")] for ilce in aktif_ilceler]
        kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_il")])
        kb.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
        await q.edit_message_text("Bolge secin:", reply_markup=InlineKeyboardMarkup(kb))
        return ILCE
    urun_ad = q.data.split(":", 1)[1]
    il      = context.user_data["il"]
    ilce    = context.user_data["ilce"]
    context.user_data["urun_ad"] = urun_ad
    urunler = ilce_urunler(il, ilce)
    gramlar = urunler.get(urun_ad, {})
    kb = [[InlineKeyboardButton(f"{g}  —  {miktar_fiyat_str(f)}", callback_data=f"gram:{g}")]
          for g, f in gramlar.items()]
    kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_ilce")])
    kb.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
    await q.edit_message_text(
        f"Il: {il}  |  Bolge: {ilce}\nUrun: {urun_ad}\n\nMiktar secin:",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    return GRAM

async def gram_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "iptal":
        await q.edit_message_text("Iptal edildi.")
        return ConversationHandler.END
    if q.data == "geri_ilce":
        il   = context.user_data["il"]
        ilce = context.user_data["ilce"]
        urunler = ilce_urunler(il, ilce)
        kb = [[InlineKeyboardButton(f"{ad}", callback_data=f"urun:{ad}")] for ad in urunler.keys()]
        kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_il")])
        kb.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
        await q.edit_message_text("Urun secin:", reply_markup=InlineKeyboardMarkup(kb))
        return URUN
    p    = q.data.split(":")
    gram = p[1]
    # Fiyatı havuzdan al
    il      = context.user_data.get("il","")
    ilce    = context.user_data.get("ilce","")
    urun_ad = context.user_data.get("urun_ad","")
    urunler = ilce_urunler(il, ilce)
    gramlar = urunler.get(urun_ad, {})
    fiyat_obj = gramlar.get(gram, {})
    tl_fiyat  = miktar_tl(fiyat_obj)
    usd_fiyat = miktar_usd(fiyat_obj)
    context.user_data["gram"]      = gram
    context.user_data["fiyat_tl"]  = tl_fiyat
    context.user_data["fiyat_usd"] = usd_fiyat
    il      = context.user_data["il"]
    ilce    = context.user_data["ilce"]
    urun_ad = context.user_data["urun_ad"]
    no      = sp_no(update.effective_user.id)
    context.user_data["no"] = no
    tl_fiyat  = context.user_data.get("fiyat_tl", 0)
    usd_fiyat = context.user_data.get("fiyat_usd", 0)
    uid       = update.effective_user.id

    # İndirim kontrolü
    indirim_aktif = musteri_indirim_var_mi(uid)
    kalan         = musteri_kalan_siparis(uid)

    if indirim_aktif:
        indirimli_tl  = indirimli_fiyat(tl_fiyat, uid)
        indirimli_usd = indirimli_fiyat(usd_fiyat, uid)
        context.user_data["fiyat_tl"]  = indirimli_tl
        context.user_data["fiyat_usd"] = indirimli_usd
        indirim_txt = f"\n🎉 %{INDIRIM_ORANI} INDIRIM UYGULANDL!\n"
        fiyat_satir = (
            f"IBAN Fiyati   : ~~{fiyat_str(tl_fiyat)}~~ {fiyat_str(indirimli_tl)} TL\n"
            f"TRC20 Fiyati  : ~~{fiyat_str(usd_fiyat)}~~ {fiyat_str(indirimli_usd)} USD\n"
        )
    else:
        indirim_txt = f"\nSonraki indiriminize {kalan} siparis kaldi!\n" if kalan > 0 else ""
        fiyat_satir = (
            f"IBAN Fiyati   : {fiyat_str(tl_fiyat)} TL\n"
            f"TRC20 Fiyati  : {fiyat_str(usd_fiyat)} USD\n"
        )

    ozet = (
        f"Siparis Ozeti\n─────────────────\n"
        f"Siparis No : {no}\n"
        f"Il         : {il}\n"
        f"Bolge      : {ilce}\n"
        f"Urun       : {urun_ad}\n"
        f"Miktar     : {gram}\n"
        f"─────────────────\n"
        f"{fiyat_satir}"
        f"─────────────────\n"
        f"{indirim_txt}\n"
        f"Odeme yontemini secin:"
    )
    kb = [
        [InlineKeyboardButton("🏦 IBAN / Havale", callback_data="odeme_iban")],
        [InlineKeyboardButton("💎 TRC20 (USDT)",  callback_data="odeme_trc20")],
        [InlineKeyboardButton("⬅️ Geri",           callback_data="geri_gram")],
        [InlineKeyboardButton("❌ Iptal",           callback_data="iptal")],
    ]
    await q.edit_message_text(ozet, reply_markup=InlineKeyboardMarkup(kb))
    return ODEME_SEC

async def odeme_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "iptal":
        await q.edit_message_text("Iptal edildi.")
        return ConversationHandler.END
    if q.data == "geri_gram":
        il      = context.user_data["il"]
        ilce    = context.user_data["ilce"]
        urun_ad = context.user_data["urun_ad"]
        urunler = ilce_urunler(il, ilce)
        gramlar = urunler.get(urun_ad, {})
        kb = [[InlineKeyboardButton(f"{g}  —  {miktar_fiyat_str(f)}", callback_data=f"gram:{g}")]
              for g, f in gramlar.items()]
        kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_ilce")])
        kb.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
        await q.edit_message_text("Miktar secin:", reply_markup=InlineKeyboardMarkup(kb))
        return GRAM
    if q.data in ("odeme_iban", "odeme_trc20"):
        context.user_data["odeme_yontemi"] = q.data
        no      = context.user_data.get("no", "?")
        urun_ad = context.user_data.get("urun_ad", "?")
        gram    = context.user_data.get("gram", "?")
        fiyat   = context.user_data.get("fiyat", 0)
        bilgi     = odeme_bilgileri.get("iban") if q.data == "odeme_iban" else odeme_bilgileri.get("trc20")
        tl_fiyat  = context.user_data.get("fiyat_tl", 0)
        usd_fiyat = context.user_data.get("fiyat_usd", 0)
        fiyat_goster = f"{fiyat_str(tl_fiyat)} TL" if q.data == "odeme_iban" else f"{fiyat_str(usd_fiyat)} USD"
        context.user_data["fiyat"] = tl_fiyat if q.data == "odeme_iban" else usd_fiyat
        ozet = (
            f"Siparis Ozeti\n─────────────────\n"
            f"Siparis No : {no}\n"
            f"Urun       : {urun_ad} {gram}\n"
            f"Fiyat      : {fiyat_goster}\n"
            f"─────────────────\n\n"
            f"{bilgi}\n\n"
            f"Odemeyi yaptiktan sonra dekont fotografini gonderin."
        )
        kb = [
            [InlineKeyboardButton("✅ Siparisi Onayla", callback_data="onayla")],
            [InlineKeyboardButton("⬅️ Geri",            callback_data="geri_odeme")],
            [InlineKeyboardButton("❌ Iptal",            callback_data="iptal")],
        ]
        await q.edit_message_text(ozet, reply_markup=InlineKeyboardMarkup(kb))
        return ODEME

async def odeme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "iptal":
        await q.edit_message_text("Iptal edildi.")
        return ConversationHandler.END
    if q.data == "geri_odeme":
        il      = context.user_data["il"]
        ilce    = context.user_data["ilce"]
        urun_ad = context.user_data["urun_ad"]
        gram    = context.user_data["gram"]
        fiyat   = context.user_data["fiyat"]
        no      = context.user_data["no"]
        ozet = (
            f"Siparis Ozeti\n─────────────────\n"
            f"Siparis No : {no}\n"
            f"Il         : {il}\n"
            f"Bolge      : {ilce}\n"
            f"Urun       : {urun_ad}\n"
            f"Miktar     : {gram}\n"
            f"Fiyat      : {fiyat_str(fiyat)}\n"
            f"─────────────────\n\nOdeme yontemini secin:"
        )
        kb = [
            [InlineKeyboardButton("🏦 IBAN / Havale", callback_data="odeme_iban")],
            [InlineKeyboardButton("💎 TRC20 (USDT)",  callback_data="odeme_trc20")],
            [InlineKeyboardButton("⬅️ Geri",           callback_data="geri_gram")],
            [InlineKeyboardButton("❌ Iptal",           callback_data="iptal")],
        ]
        await q.edit_message_text(ozet, reply_markup=InlineKeyboardMarkup(kb))
        return ODEME_SEC
    if q.data == "onayla":
        no = context.user_data.get("no", "?")
        siparisler[no] = {
            "user_id": update.effective_user.id,
            "il":      context.user_data["il"],
            "ilce":    context.user_data["ilce"],
            "urun":    f"{context.user_data['urun_ad']} {context.user_data['gram']}",
            "urun_ad": context.user_data["urun_ad"],
            "gram":    context.user_data["gram"],
            "fiyat":   context.user_data["fiyat"],
            "odeme":   context.user_data.get("odeme_yontemi", ""),
            "durum":   "beklemede"
        }
        kaydet(S_DOSYA, siparisler)
        yontem = "Havale/EFT" if context.user_data.get("odeme_yontemi") == "odeme_iban" else "TRC20 (USDT)"
        await q.edit_message_text(
            f"Siparisıniz alindi!\n\nSiparis No: {no}\n\n"
            f"Odeme yontemi: {yontem}\n"
            f"Odemeyi yapip dekontu gonderin.\n\nTesekkurler!"
        )
        return ConversationHandler.END

# ─── DEKONT ──────────────────────────────────────────────────────────────────
async def foto_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid == ADMIN_ID:
        if uid in adm and adm[uid].get("adim") == "foto":
            adm[uid]["foto_id"] = update.message.photo[-1].file_id
            adm[uid]["adim"]    = "konum"
            await update.message.reply_text("Fotograf kaydedildi!\n\nSimdi konumu gonder:")
        else:
            await update.message.reply_text(f"Fotograf ID:\n{update.message.photo[-1].file_id}")
        return
    no      = context.user_data.get("no")
    il      = context.user_data.get("il", "?")
    ilce    = context.user_data.get("ilce", "?")
    urun_ad = context.user_data.get("urun_ad", "?")
    gram    = context.user_data.get("gram", "?")
    fiyat_v = context.user_data.get("fiyat", 0)
    if not no:
        for n, s in siparisler.items():
            if str(s["user_id"]) == str(uid) and s["durum"] == "beklemede":
                no      = n
                il      = s.get("il", il)
                ilce    = s.get("ilce", ilce)
                urun_ad = s.get("urun_ad", urun_ad)
                gram    = s.get("gram", gram)
                fiyat_v = s.get("fiyat", fiyat_v)
                break
    if not no or no not in siparisler:
        await update.message.reply_text("Aktif siparisıniz yok. Oncelikle /start ile siparis olusturun.")
        return
    kb = [[InlineKeyboardButton(f"✅ Onayla — {no}", callback_data=f"onay:{no}")]]
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=update.message.photo[-1].file_id,
        caption=(
            f"Yeni Dekont!\n\nNo: {no}\n"
            f"Il/Ilce: {il}/{ilce}\n"
            f"Urun: {urun_ad} {gram}\n"
            f"Fiyat: {fiyat_str(fiyat_v)}\n\nOnaylamak icin butona bas:"
        ),
        reply_markup=InlineKeyboardMarkup(kb)
    )
    await update.message.reply_text(f"Dekontunuz alindi! Siparis No: {no}")

# ─── KONUM GELDİĞİNDE ────────────────────────────────────────────────────────
async def konum_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_ID:
        return
    if uid not in adm or adm[uid].get("adim") != "konum":
        await update.message.reply_text("Aktif konum ekleme islemi yok.")
        return
    islem   = adm[uid]
    il      = islem["il"]
    ilce    = islem["ilce"]
    foto_id = islem["foto_id"]
    lat     = update.message.location.latitude
    lon     = update.message.location.longitude
    yeni = {"id": k_id(), "lat": lat, "lon": lon, "foto_id": foto_id, "silindi": False, "urun": {}}
    if il not in konumlar:
        konumlar[il] = {}
    if ilce not in konumlar[il]:
        konumlar[il][ilce] = []
    konumlar[il][ilce].append(yeni)
    kaydet(K_DOSYA, konumlar)
    kidx = len(konumlar[il][ilce]) - 1
    adm[uid] = {"adim": "urun_sec", "il": il, "ilce": ilce, "kidx": kidx}
    # Havuzdan ürün seç
    kb = [[InlineKeyboardButton(f"🍬 {u['ad']}", callback_data=f"ks:{hid}:{il}:{ilce}:{kidx}")]
          for hid, u in havuz.items()]
    await update.message.reply_text(
        f"Konum kaydedildi!\n\nBu konumdaki urunu sec:",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# ─── ADMİN CALLBACK ──────────────────────────────────────────────────────────
async def adm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("Yetkisiz!", show_alert=True)
        return
    await q.answer()
    d = q.data

    # Konum için ürün seç
    if d.startswith("ks:"):
        p    = d.split(":")
        hid  = p[1]
        il   = p[2]
        ilce = p[3]
        kidx = int(p[4])
        u    = havuz.get(hid, {})
        if not u or not isinstance(u, dict):
            await q.answer("Urun bulunamadi!", show_alert=True)
            return
        ad      = u.get("ad", "?")
        gramlar = u.get("miktarlar", {})
        if not gramlar:
            await q.answer("Bu urunde miktar tanimlanmamis!", show_alert=True)
            return
        adm[ADMIN_ID] = {"adim": "gramaj_sec", "il": il, "ilce": ilce, "kidx": kidx, "urun_ad": ad, "hid": hid}
        kb = [[InlineKeyboardButton(f"{g}  —  {miktar_fiyat_str(f)}", callback_data=f"ksg:{hid}:{g}:{il}:{ilce}:{kidx}")]
              for g, f in gramlar.items()]
        await q.edit_message_text(f"Urun: {ad}\n\nGramaji sec:", reply_markup=InlineKeyboardMarkup(kb))

    # Konum için gramaj seç
    elif d.startswith("ksg:"):
        p    = d.split(":")
        hid  = p[1]
        gram = p[2]
        il   = p[3]
        ilce = p[4]
        kidx = int(p[5])
        # Havuzdan ürün ve fiyatı al
        hu        = havuz.get(hid, {})
        ad        = hu.get("ad", "?") if isinstance(hu, dict) else "?"
        fiyat_obj = hu.get("miktarlar", {}).get(gram, {}) if isinstance(hu, dict) else {}
        konumlar[il][ilce][kidx]["urun"] = {"ad": ad, "gram": gram, "fiyat": fiyat_obj}
        kaydet(K_DOSYA, konumlar)
        if ADMIN_ID in adm:
            del adm[ADMIN_ID]
        kalan = ilce_konum_sayisi(il, ilce)
        fiyat_goster = miktar_fiyat_str(fiyat_obj)
        kb = [
            [InlineKeyboardButton("📍 Ayni Ilceye Yeni Konum", callback_data=f"yeni_k:{il}:{ilce}")],
            [InlineKeyboardButton("✅ Tamamlandi",              callback_data="tamam")],
        ]
        await q.edit_message_text(
            f"Kaydedildi!\n\n{il}/{ilce}\nUrun: {ad}\nGram: {gram}\nFiyat: {fiyat_goster}\n\n"
            f"Bu ilcede {kalan} aktif konum var.",
            reply_markup=InlineKeyboardMarkup(kb)
        )

    elif d.startswith("yeni_k:"):
        p    = d.split(":")
        il   = p[1]
        ilce = p[2]
        adm[ADMIN_ID] = {"adim": "foto", "il": il, "ilce": ilce}
        await q.edit_message_text(f"{il}/{ilce} icin yeni konum.\n\nFotografi gonder:")

    elif d == "tamam":
        await q.edit_message_text("Tamamlandi! /konum_ekle ile yeni konum ekleyebilirsin.")

    # Sipariş onayla
    elif d.startswith("onay:"):
        no = d.split(":")[1]
        s  = siparisler.get(no)
        if not s:
            await q.edit_message_caption(f"{no} bulunamadi.")
            return
        if s["durum"] in ("isleniyor", "tamamlandi"):
            await q.answer(f"Bu siparis zaten {s['durum']}!", show_alert=True)
            return
        il      = s["il"]
        ilce    = s["ilce"]
        urun_ad = s["urun_ad"]
        gram    = s["gram"]
        k = ilce_konum_bul(il, ilce, urun_ad, gram)
        if not k:
            await q.edit_message_caption(f"{il}/{ilce} bolgesinde bu urun icin musait konum kalmadi!\n/konum_ekle ile ekleyin.")
            return
        siparisler[no]["durum"] = "isleniyor"
        kaydet(S_DOSYA, siparisler)
        mid = s["user_id"]
        await context.bot.send_photo(
            chat_id=mid, photo=k["foto_id"],
            caption=f"Siparisıniz hazirlandi!\n\nSiparis No: {no}\nAsagidaki konumdan teslim alabilirsiniz."
        )
        await context.bot.send_location(chat_id=mid, latitude=k["lat"], longitude=k["lon"])
        await context.bot.send_message(chat_id=mid, text=f"Siparisıniz teslimata hazir!\n\nSiparis No: {no}\n\nIyi gunler!")
        for km in konumlar.get(il, {}).get(ilce, []):
            if km["id"] == k["id"]:
                km["silindi"] = True
                break
        kaydet(K_DOSYA, konumlar)
        siparisler[no]["durum"] = "tamamlandi"
        kaydet(S_DOSYA, siparisler)

        # Müşteri takibini güncelle
        musteri_ad = s.get("musteri_ad", "")
        musteri_guncelle(mid, musteri_ad)
        yeni_tamamlanan = musteri_tamamlanan(mid)
        yeni_kalan      = musteri_kalan_siparis(mid)

        # Müşteriye bildirim gönder
        if yeni_kalan == 0:
            # Bir sonraki sipariş indirimli olacak
            await context.bot.send_message(
                chat_id=mid,
                text=(
                    f"Tebrikler! {yeni_tamamlanan}. siparisini tamamladin!\n\n"
                    f"Bir sonraki siparisinde %{INDIRIM_ORANI} indirim kazandin!"
                )
            )
        elif yeni_kalan <= 2:
            await context.bot.send_message(
                chat_id=mid,
                text=(
                    f"%{INDIRIM_ORANI} indirim icin {yeni_kalan} siparisin kaldi!"
                )
            )

        kalan = ilce_konum_sayisi(il, ilce)
        uyari = f"\n\n{il}/{ilce} bolgesinde {kalan} konum kaldi!" if kalan <= 3 else ""
        await q.edit_message_caption(
            f"Tamamlandi! {no}\nMusteri toplam: {yeni_tamamlanan} siparis{uyari}"
        )

# ─── ADMİN: /konum_ekle ──────────────────────────────────────────────────────
async def konum_ekle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    iller = list(konumlar.keys())
    kb    = [[InlineKeyboardButton(f"📍 {il}", callback_data=f"ke_il:{il}")] for il in iller]
    kb.append([InlineKeyboardButton("➕ Yeni Il", callback_data="ke_yeni_il")])
    await update.message.reply_text("Il sec:", reply_markup=InlineKeyboardMarkup(kb))

async def ke_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("Yetkisiz!", show_alert=True)
        return
    await q.answer()
    d = q.data
    if d == "ke_yeni_il":
        adm[ADMIN_ID] = {"adim": "yeni_il"}
        await q.edit_message_text("Yeni il adini yaz:")
    elif d.startswith("ke_il:"):
        il      = d.split(":", 1)[1]
        ilceler = list(konumlar.get(il, {}).keys())
        kb = [[InlineKeyboardButton(f"📌 {ilce}", callback_data=f"ke_ilce:{il}:{ilce}")] for ilce in ilceler]
        kb.append([InlineKeyboardButton("➕ Yeni Ilce", callback_data=f"ke_yeni_ilce:{il}")])
        await q.edit_message_text(f"Il: {il}\n\nIlce sec:", reply_markup=InlineKeyboardMarkup(kb))
    elif d.startswith("ke_yeni_ilce:"):
        il = d.split(":", 1)[1]
        adm[ADMIN_ID] = {"adim": "yeni_ilce", "il": il}
        await q.edit_message_text(f"{il} icin ilce adini yaz:")
    elif d.startswith("ke_ilce:"):
        p    = d.split(":")
        il   = p[1]
        ilce = p[2]
        adm[ADMIN_ID] = {"adim": "foto", "il": il, "ilce": ilce}
        await q.edit_message_text(f"{il} / {ilce}\n\nFotografi gonder:")

# ─── ADMİN: /urunler ─────────────────────────────────────────────────────────

async def goster_havuz(q):
    msg = "Urun Havuzu\n─────────────────\n"
    for hid, u in havuz.items():
        ad        = u["ad"] if isinstance(u, dict) else u
        tip       = u.get("tip", "gram") if isinstance(u, dict) else "gram"
        miktarlar = u.get("miktarlar", {}) if isinstance(u, dict) else {}
        mik_txt   = "  ".join([f"{m}: {miktar_fiyat_str(f)}" for m, f in miktarlar.items()]) if miktarlar else "Miktar yok"
        msg += f"\n{ad} [{tip_label(tip)}]\n  {mik_txt}\n"
    msg += "\nDuzenlemek icin secin:"
    kb = [[InlineKeyboardButton(f"{u['ad'] if isinstance(u,dict) else u}", callback_data=f"u_detay:{hid}")]
          for hid, u in havuz.items()]
    kb.append([InlineKeyboardButton("➕ Yeni Urun Ekle", callback_data="u_ekle")])
    if hasattr(q, 'edit_message_text'):
        await q.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await q.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb))

async def urunler_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await goster_havuz(update.message)

async def urun_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("Yetkisiz!", show_alert=True)
        return
    await q.answer()
    d = q.data

    # ── Yeni ürün ekle ──
    if d == "u_ekle":
        adm[ADMIN_ID] = {"adim": "u_ad"}
        await q.edit_message_text("Yeni urun adini yaz (örn: Skunk, Crystall):")

    # ── Tip seç ──
    elif d.startswith("u_tip_"):
        tip = d.replace("u_tip_", "")
        adm[ADMIN_ID]["tip"]  = tip
        adm[ADMIN_ID]["adim"] = "u_miktar"
        ad = adm[ADMIN_ID].get("urun_ad", "?")
        if tip == "gram":
            ipucu = "örn: 1g, 3.5g, 7g"
        elif tip == "tekli":
            ipucu = "örn: 1 Adet, 5 Adet"
        else:
            ipucu = "örn: 1 Kutu, 5 Kutu"
        await q.edit_message_text(
            f"Urun: {ad}  [{tip_label(tip)}]\n\nMiktar yaz ({ipucu}):"
        )

    # ── Ürün detay ──
    elif d.startswith("u_detay:"):
        hid       = d.split(":")[1]
        u         = havuz.get(hid, {})
        ad        = u["ad"] if isinstance(u, dict) else u
        tip       = u.get("tip", "gram") if isinstance(u, dict) else "gram"
        miktarlar = u.get("miktarlar", {}) if isinstance(u, dict) else {}
        mik_txt   = "\n".join([f"  {m}: {miktar_fiyat_str(f)}" for m, f in miktarlar.items()]) if miktarlar else "  Miktar yok"
        kb = [
            [InlineKeyboardButton("➕ Miktar/Fiyat Ekle", callback_data=f"u_mik_ekle:{hid}")],
            [InlineKeyboardButton("➖ Miktar Sil",        callback_data=f"u_mik_sil:{hid}")],
            [InlineKeyboardButton("🗑 Urunu Sil",         callback_data=f"u_sil:{hid}")],
            [InlineKeyboardButton("⬅️ Geri",              callback_data="u_geri")],
        ]
        await q.edit_message_text(
            f"{ad}  [{tip_label(tip)}]\n\nMiktar / Fiyat:\n{mik_txt}\n\nNe yapmak istiyorsun?",
            reply_markup=InlineKeyboardMarkup(kb)
        )

    # ── Geri ──
    elif d == "u_geri":
        await goster_havuz(q)

    # ── Mevcut ürüne miktar ekle ──
    elif d.startswith("u_mik_ekle:"):
        hid = d.split(":")[1]
        u   = havuz.get(hid, {})
        tip = u.get("tip", "gram") if isinstance(u, dict) else "gram"
        if tip == "gram":
            ipucu = "örn: 7g, 14g"
        elif tip == "tekli":
            ipucu = "örn: 10 Adet"
        else:
            ipucu = "örn: 3 Kutu"
        adm[ADMIN_ID] = {"adim": "u_miktar", "hid": hid, "yeni": False}
        await q.edit_message_text(f"Eklenecek miktari yaz ({ipucu}):")

    # ── Miktar sil ──
    elif d.startswith("u_mik_sil:"):
        hid       = d.split(":")[1]
        u         = havuz.get(hid, {})
        miktarlar = u.get("miktarlar", {}) if isinstance(u, dict) else {}
        if not miktarlar:
            await q.answer("Silinecek miktar yok!", show_alert=True)
            return
        kb = [[InlineKeyboardButton(f"🗑 {m} — {miktar_fiyat_str(f)}", callback_data=f"u_mik_sil2:{hid}:{m}")]
              for m, f in miktarlar.items()]
        kb.append([InlineKeyboardButton("⬅️ Geri", callback_data=f"u_detay:{hid}")])
        await q.edit_message_text("Hangi miktari silmek istiyorsun?", reply_markup=InlineKeyboardMarkup(kb))

    elif d.startswith("u_mik_sil2:"):
        p   = d.split(":")
        hid = p[1]
        mik = p[2]
        u   = havuz.get(hid, {})
        if isinstance(u, dict) and mik in u.get("miktarlar", {}):
            del u["miktarlar"][mik]
            kaydet(H_DOSYA, havuz)
        await q.edit_message_text(f"'{mik}' silindi!")

    # ── Ürün sil ──
    elif d.startswith("u_sil:"):
        hid = d.split(":")[1]
        u   = havuz.pop(hid, {})
        ad  = u["ad"] if isinstance(u, dict) else u
        kaydet(H_DOSYA, havuz)
        await q.edit_message_text(f"'{ad}' urun havuzundan silindi!")

    # ── Başka miktar ekle ──
    elif d == "u_gramaj_devam":
        tip = adm.get(ADMIN_ID, {}).get("tip", "gram")
        adm[ADMIN_ID]["adim"] = "u_miktar"
        if tip == "gram":
            ipucu = "örn: 7g, 14g"
        elif tip == "tekli":
            ipucu = "örn: 10 Adet"
        else:
            ipucu = "örn: 3 Kutu"
        await q.edit_message_text(f"Yeni miktari yaz ({ipucu}):")

    # ── Kaydet ──
    elif d == "u_gramaj_kaydet":
        islem    = adm.get(ADMIN_ID, {})
        ad       = islem.get("urun_ad", "")
        hid      = islem.get("hid", f"h{int(time.time())}")
        tip      = islem.get("tip", "gram")
        miktarlar = islem.get("miktarlar", {})
        havuz[hid] = {"ad": ad, "tip": tip, "miktarlar": miktarlar}
        kaydet(H_DOSYA, havuz)
        if ADMIN_ID in adm:
            del adm[ADMIN_ID]
        mik_txt = "  ".join([f"{m}: {miktar_fiyat_str(f)}" for m, f in miktarlar.items()])
        await q.edit_message_text(
            f"'{ad}' [{tip_label(tip)}] eklendi!\n\n{mik_txt}\n\n/urunler ile urun listesini gorebilirsin."
        )


# ─── ADMİN METİN ─────────────────────────────────────────────────────────────
async def metin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = update.message.text.strip()

    if uid == ADMIN_ID and uid in adm:
        a = adm[uid]

        if a["adim"] == "yeni_il":
            if txt not in konumlar:
                konumlar[txt] = {}
                kaydet(K_DOSYA, konumlar)
            del adm[uid]
            iller = list(konumlar.keys())
            kb = [[InlineKeyboardButton(f"📍 {il}", callback_data=f"ke_il:{il}")] for il in iller]
            kb.append([InlineKeyboardButton("➕ Yeni Il", callback_data="ke_yeni_il")])
            await update.message.reply_text(f"'{txt}' eklendi! Il sec:", reply_markup=InlineKeyboardMarkup(kb))
            return

        elif a["adim"] == "yeni_ilce":
            il = a["il"]
            if il not in konumlar:
                konumlar[il] = {}
            if txt not in konumlar[il]:
                konumlar[il][txt] = []
                kaydet(K_DOSYA, konumlar)
            adm[uid] = {"adim": "foto", "il": il, "ilce": txt}
            await update.message.reply_text(f"'{txt}' eklendi!\n\nFotografi gonder:")
            return

        elif a["adim"] == "u_ad":
            adm[uid] = {"adim": "u_tip_bekleniyor", "urun_ad": txt, "hid": f"h{int(time.time())}", "miktarlar": {}, "yeni": True}
            kb = [
                [InlineKeyboardButton("⚖️ Gram",         callback_data="u_tip_gram")],
                [InlineKeyboardButton("1️⃣ Tekli (Adet)", callback_data="u_tip_tekli")],
                [InlineKeyboardButton("📦 Kutu",          callback_data="u_tip_kutu")],
            ]
            await update.message.reply_text(f"Urun: {txt}\n\nSatis tipini sec:", reply_markup=InlineKeyboardMarkup(kb))
            return

        elif a["adim"] == "u_miktar":
            adm[uid]["gecici_miktar"] = txt
            adm[uid]["adim"]          = "u_fiyat_tl"
            await update.message.reply_text(f"'{txt}' icin TL fiyatini yaz (örn: 450):")
            return

        elif a["adim"] == "u_fiyat_tl":
            try:
                tl = float(txt.replace(",", "."))
                adm[uid]["gecici_tl"] = tl
                adm[uid]["adim"]      = "u_fiyat_usd"
                await update.message.reply_text(f"'{a['gecici_miktar']}' icin Dolar (USD) fiyatini yaz (örn: 14):")
            except ValueError:
                await update.message.reply_text("Gecersiz fiyat! Sayi gir (örn: 450)")
            return

        elif a["adim"] == "u_fiyat_usd":
            try:
                usd = float(txt.replace(",", "."))
                tl  = a.get("gecici_tl", 0)
                m   = a.get("gecici_miktar", "?")
                fiyat_obj = {"tl": tl, "usd": usd}
                if a.get("yeni"):
                    if "miktarlar" not in a:
                        a["miktarlar"] = {}
                    a["miktarlar"][m] = fiyat_obj
                    a["adim"] = "u_devam"
                    mik_txt = "  ".join([f"{mk}: {miktar_fiyat_str(fv)}" for mk, fv in a["miktarlar"].items()])
                    kb = [
                        [InlineKeyboardButton("➕ Baska Miktar Ekle", callback_data="u_gramaj_devam")],
                        [InlineKeyboardButton("✅ Kaydet",             callback_data="u_gramaj_kaydet")],
                    ]
                    await update.message.reply_text(
                        f"Eklendi!\n\nMevcut:\n{mik_txt}",
                        reply_markup=InlineKeyboardMarkup(kb)
                    )
                else:
                    hid = a["hid"]
                    if isinstance(havuz.get(hid), dict):
                        havuz[hid]["miktarlar"][m] = fiyat_obj
                        kaydet(H_DOSYA, havuz)
                    del adm[uid]
                    await update.message.reply_text(f"'{m}: {miktar_fiyat_str(fiyat_obj)}' eklendi!")
            except ValueError:
                await update.message.reply_text("Gecersiz fiyat! Sayi gir (örn: 14)")
            return

        elif a["adim"] == "iban_guncelle":
            odeme_bilgileri["iban"] = "Odeme Yontemi: IBAN / Havale\n─────────────────\n" + txt
            kaydet(O_DOSYA, odeme_bilgileri)
            del adm[uid]
            await update.message.reply_text("IBAN bilgileri guncellendi!")
            return

        elif a["adim"] == "trc20_guncelle":
            odeme_bilgileri["trc20"] = "Odeme Yontemi: TRC20 (USDT)\n─────────────────\nAdres: " + txt + "\n\nGondermeden once adresi kontrol edin!"
            kaydet(O_DOSYA, odeme_bilgileri)
            del adm[uid]
            await update.message.reply_text("TRC20 adresi guncellendi!")
            return

    await update.message.reply_text("Siparis vermek icin /start yazin.")


# ─── ADMİN: /odeme ───────────────────────────────────────────────────────────
async def odeme_yonetim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    kb = [
        [InlineKeyboardButton("🏦 IBAN Bilgilerini Duzenle",  callback_data="ody_iban")],
        [InlineKeyboardButton("💎 TRC20 Adresini Duzenle",    callback_data="ody_trc20")],
    ]
    await update.message.reply_text(
        f"Odeme Bilgileri\n─────────────────\n\n"
        f"IBAN:\n{odeme_bilgileri.get('iban','')}\n\n"
        f"─────────────────\n\n"
        f"TRC20:\n{odeme_bilgileri.get('trc20','')}\n\n"
        f"─────────────────\nDuzenlemek istedigin yontemi sec:",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def odeme_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("Yetkisiz!", show_alert=True)
        return
    await q.answer()
    if q.data == "ody_iban":
        adm[ADMIN_ID] = {"adim": "iban_guncelle"}
        await q.edit_message_text("Yeni IBAN bilgilerini yaz:\n\nOrnek:\nBanka: Ziraat\nHesap Adi: Ad Soyad\nIBAN: TR00...")
    elif q.data == "ody_trc20":
        adm[ADMIN_ID] = {"adim": "trc20_guncelle"}
        await q.edit_message_text("Yeni TRC20 adresini yaz:")


# ─── ADMİN: /musteriler ──────────────────────────────────────────────────────
async def musteriler_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not musteriler:
        await update.message.reply_text("Henuz musteri yok.")
        return
    msg = "Musteri Listesi\n─────────────────\n"
    for uid, m in sorted(musteriler.items(), key=lambda x: -x[1].get("tamamlanan", 0)):
        t     = m.get("tamamlanan", 0)
        ad    = m.get("ad", "?")
        kalan = INDIRIM_HER_N_SIPARIS - (t % INDIRIM_HER_N_SIPARIS)
        kalan = 0 if kalan == INDIRIM_HER_N_SIPARIS else kalan
        indirim = "INDIRIM HAKKL VAR!" if t > 0 and t % INDIRIM_HER_N_SIPARIS == 0 else f"{kalan} siparis kaldi"
        msg += f"\n👤 {ad} (ID:{uid})\n  Tamamlanan: {t} siparis\n  Durum: {indirim}\n"
    await update.message.reply_text(msg)

# ─── GÜN SONU ────────────────────────────────────────────────────────────────
async def gunsonu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    bugun = time.strftime("%d.%m.%Y")
    saat  = time.strftime("%H:%M")
    toplam_siparis = tamamlanan = bekleyen = 0
    toplam_gelir = iban_gelir = trc20_gelir = 0.0
    iban_adet = trc20_adet = 0
    urun_sayac = {}
    for no, s in siparisler.items():
        toplam_siparis += 1
        durum = s.get("durum", "")
        fiyat = float(s.get("fiyat", 0))
        odeme = s.get("odeme", "")
        urun  = s.get("urun", "?")
        if durum == "tamamlandi":
            tamamlanan   += 1
            toplam_gelir += fiyat
            if odeme == "odeme_iban":
                iban_gelir += fiyat
                iban_adet  += 1
            elif odeme == "odeme_trc20":
                trc20_gelir += fiyat
                trc20_adet  += 1
            urun_sayac[urun] = urun_sayac.get(urun, 0) + 1
        elif durum == "beklemede":
            bekleyen += 1
    toplam_konum = kalan_konum = kullanilan_konum = 0
    konum_satirlar = []
    for il, ilceler in konumlar.items():
        for ilce, liste in ilceler.items():
            for k in liste:
                toplam_konum += 1
                if k.get("silindi"):
                    kullanilan_konum += 1
                else:
                    kalan_konum += 1
            aktif = ilce_konum_sayisi(il, ilce)
            e = "🟢" if aktif > 3 else ("🟡" if aktif > 0 else "🔴")
            konum_satirlar.append(f"  {e} {il}/{ilce}: {aktif} kalan / {len(liste)} toplam")
    urun_satirlar = [f"  {u}: {a} adet" for u, a in sorted(urun_sayac.items(), key=lambda x: -x[1])] or ["  Satilan urun yok"]
    konum_txt = "\n".join(konum_satirlar) if konum_satirlar else "  Konum yok"
    urun_txt  = "\n".join(urun_satirlar)
    rapor  = f"📊 GUN SONU RAPORU\nTarih: {bugun} {saat}\n"
    rapor += "═══════════════════\n\n"
    rapor += "📦 SIPARIS OZETI\n─────────────────\n"
    rapor += f"Toplam Siparis : {toplam_siparis}\n"
    rapor += f"Tamamlanan     : {tamamlanan}\n"
    rapor += f"Bekleyen       : {bekleyen}\n\n"
    rapor += "💰 GELIR OZETI\n─────────────────\n"
    rapor += f"Toplam Gelir   : {fiyat_str(toplam_gelir)}\n"
    rapor += f"IBAN/Havale    : {fiyat_str(iban_gelir)} ({iban_adet} siparis)\n"
    rapor += f"TRC20 (USDT)   : {fiyat_str(trc20_gelir)} ({trc20_adet} siparis)\n\n"
    rapor += "🍬 URUN SATISLARI\n─────────────────\n"
    rapor += urun_txt + "\n\n"
    rapor += "📍 KONUM DURUMU\n─────────────────\n"
    rapor += f"Toplam Konum   : {toplam_konum}\n"
    rapor += f"Kalan          : {kalan_konum}\n"
    rapor += f"Kullanilan     : {kullanilan_konum}\n\n"
    rapor += konum_txt + "\n\n"
    rapor += "═══════════════════"
    kb = [[InlineKeyboardButton("🗑 Siparisleri Sifirla", callback_data="gunsonu_sifirla")]]
    await update.message.reply_text(rapor, reply_markup=InlineKeyboardMarkup(kb))

async def gunsonu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("Yetkisiz!", show_alert=True)
        return
    await q.answer()
    if q.data == "gunsonu_sifirla":
        kb = [
            [InlineKeyboardButton("✅ Evet, Sifirla", callback_data="gunsonu_evet")],
            [InlineKeyboardButton("❌ Iptal",          callback_data="gunsonu_iptal")],
        ]
        await q.edit_message_text("Emin misin?\n\nTum siparisler silinecek.\nKonum ve urun bilgileri korunacak.", reply_markup=InlineKeyboardMarkup(kb))
    elif q.data == "gunsonu_evet":
        siparisler.clear()
        kaydet(S_DOSYA, siparisler)
        await q.edit_message_text(f"Siparisler sifirland!\n\nTarih: {time.strftime('%d.%m.%Y %H:%M')}\nYeni gun basliyor.")
    elif q.data == "gunsonu_iptal":
        await q.edit_message_text("Iptal edildi.")

# ─── ADMİN: /konumlar ────────────────────────────────────────────────────────
async def konumlar_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not konumlar:
        await update.message.reply_text("Hic konum yok. /konum_ekle ile ekle.")
        return
    for il, ilceler in konumlar.items():
        for ilce, liste in ilceler.items():
            kalan = ilce_konum_sayisi(il, ilce)
            e   = "🟢" if kalan > 3 else ("🟡" if kalan > 0 else "🔴")
            msg = f"{e} {il} / {ilce}\nAktif: {kalan} / Toplam: {len(liste)}\n─────────────────"
            aktif_no = 0
            for k in liste:
                if k.get("silindi"):
                    continue
                aktif_no += 1
                u = k.get("urun", {})
                msg += (
                    f"\n\n#{aktif_no} Konum\n"
                    f"  Urun  : {u.get('ad','?')}\n"
                    f"  Gram  : {u.get('gram','?')}\n"
                    f"  Fiyat : {miktar_fiyat_str(u.get('fiyat',{}))}\n"
                    f"  Konum : {k.get('lat',0):.4f}, {k.get('lon',0):.4f}"
                )
            if aktif_no == 0:
                msg += "\n\nBu ilcede aktif konum yok."
            await update.message.reply_text(msg)

async def siparisler_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not siparisler:
        await update.message.reply_text("Henuz siparis yok.")
        return
    e = {"beklemede": "⏳", "isleniyor": "🔄", "tamamlandi": "✅"}
    msg = "Siparisler\n─────────────────\n"
    for no, s in siparisler.items():
        msg += f"\n{e.get(s['durum'],'?')} {no}\n  {s.get('il','')}/{s.get('ilce','')} | {s['urun']} | {fiyat_str(s['fiyat'])}\n"
    await update.message.reply_text(msg)

async def iptal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Iptal edildi. /start ile yeniden baslayin.")
    return ConversationHandler.END

# ─── MAIN ────────────────────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            IL:        [CallbackQueryHandler(il_sec)],
            ILCE:      [CallbackQueryHandler(ilce_sec)],
            URUN:      [CallbackQueryHandler(urun_sec)],
            GRAM:      [CallbackQueryHandler(gram_sec)],
            ODEME_SEC: [CallbackQueryHandler(odeme_sec)],
            ODEME:     [CallbackQueryHandler(odeme)],
        },
        fallbacks=[CommandHandler("iptal", iptal)],
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("siparisler", siparisler_goster))
    app.add_handler(CommandHandler("konumlar",   konumlar_goster))
    app.add_handler(CommandHandler("konum_ekle", konum_ekle))
    app.add_handler(CommandHandler("urunler",    urunler_goster))
    app.add_handler(CommandHandler("odeme",      odeme_yonetim))
    app.add_handler(CommandHandler("gunsonu",    gunsonu))
    app.add_handler(CommandHandler("musteriler", musteriler_goster))

    app.add_handler(CallbackQueryHandler(adm_cb,         pattern=r"^(ks:|ksg:|yeni_k:|tamam|onay:)"))
    app.add_handler(CallbackQueryHandler(ke_cb,          pattern=r"^ke_"))
    app.add_handler(CallbackQueryHandler(urun_cb,        pattern=r"^u_"))
    app.add_handler(CallbackQueryHandler(odeme_cb,       pattern=r"^ody_"))
    app.add_handler(CallbackQueryHandler(gunsonu_cb,     pattern=r"^gunsonu_"))

    app.add_handler(MessageHandler(filters.PHOTO,    foto_al))
    app.add_handler(MessageHandler(filters.LOCATION, konum_al))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, metin))

    logger.info(f"Bot basladi. Siparis:{len(siparisler)} Havuz:{len(havuz)}")
    app.run_polling()

if __name__ == "__main__":
    main()
