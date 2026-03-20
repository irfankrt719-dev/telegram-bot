"""
Telegram Sipariş Botu - Temiz Versiyon
"""
import logging, json, os, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters, ConversationHandler
)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "BURAYA_TOKEN")
ADMIN_ID  = int(os.environ.get("ADMIN_ID", "123456789"))

IL, ILCE, URUN, GRAM, ODEME_SEC, ODEME = range(6)
adm = {}

S_DOSYA = "siparisler.json"
K_DOSYA = "konumlar.json"
H_DOSYA = "havuz.json"
O_DOSYA = "odeme.json"
M_DOSYA = "musteriler.json"
A_DOSYA = "ayarlar.json"

HAVUZ_VARSAYILAN = {
    "h1": {"ad": "Deneme 1", "tip": "gram",  "miktarlar": {"2.5": {"tl": 4000.0, "usd": 80.0}, "5": {"tl": 7000.0, "usd": 150.0}}},
    "h2": {"ad": "Deneme 2", "tip": "tekli", "miktarlar": {"Jilet": {"tl": 2000.0, "usd": 40.0}, "Kutu": {"tl": 7000.0, "usd": 150.0}}}
}
ODEME_VARSAYILAN = {
    "iban":  "Odeme Yontemi: IBAN / Havale\n─────────────────\nBanka: Ziraat Bankasi\nHesap Adi: Sirket Adi\nIBAN: TR00 0000 0000 0000 0000 0000 00\n\nAciklama kismina siparis numaranizi yazin!",
    "trc20": "Odeme Yontemi: TRC20 (USDT)\n─────────────────\nAdres: BURAYA_TRC20_ADRESINIZI_YAZIN\n\nGondermeden once adresi kontrol edin!"
}
AYARLAR_VARSAYILAN = {
    "giris_foto_id": "",
    "kanal_link":    "https://t.me/kanaliniz",
    "destek_link":   "https://t.me/destekkullanici",
    "market_kurali": "Market kurallari henuz yazilmamis."
}

INDIRIM_HER_N = 5
INDIRIM_ORANI = 10

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
ayarlar         = yukle(A_DOSYA, AYARLAR_VARSAYILAN)

for d, v in [(H_DOSYA, havuz), (O_DOSYA, odeme_bilgileri), (M_DOSYA, musteriler), (A_DOSYA, ayarlar)]:
    if not os.path.exists(d):
        kaydet(d, v)

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

def miktar_fiyat_str(obj):
    if isinstance(obj, dict):
        return f"{fiyat_str(obj.get('tl',0))}₺ / {fiyat_str(obj.get('usd',0))}$"
    return fiyat_str(obj)

def miktar_tl(obj):
    return float(obj.get("tl", 0)) if isinstance(obj, dict) else float(obj)

def miktar_usd(obj):
    return float(obj.get("usd", 0)) if isinstance(obj, dict) else float(obj)

def tip_label(tip):
    return {"gram": "Gram", "tekli": "Tekli (Adet)", "kutu": "Kutu"}.get(tip, tip)

def ilce_aktif_konumlar(il, ilce):
    return [k for k in konumlar.get(il, {}).get(ilce, [])
            if not k.get("silindi") and k.get("foto_id") and k.get("urun")]

def ilce_urunler(il, ilce):
    """Sadece rezervesiz konumların ürünlerini göster"""
    sonuc = {}
    for k in konumlar.get(il, {}).get(ilce, []):
        if k.get("silindi") or k.get("rezerve") or not k.get("foto_id") or not k.get("urun"):
            continue
        u  = k.get("urun", {})
        ad = u.get("ad", "?")
        g  = str(u.get("gram", "?"))
        raw = u.get("fiyat", 0)
        f = raw if isinstance(raw, dict) else {"tl": float(raw), "usd": 0}
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
    """Toplam aktif konum (rezerveli + boş)"""
    return len(ilce_aktif_konumlar(il, ilce))

def ilce_bos_konum_sayisi(il, ilce):
    """Sadece rezervesiz boş konumlar"""
    return sum(1 for k in konumlar.get(il, {}).get(ilce, [])
               if not k.get("silindi") and not k.get("rezerve") and k.get("foto_id") and k.get("urun"))

def ilce_bos_konum_bul(il, ilce, urun_ad, gram):
    """Rezervesiz ilk uygun konumu bul"""
    for k in konumlar.get(il, {}).get(ilce, []):
        if k.get("silindi") or k.get("rezerve"):
            continue
        u = k.get("urun", {})
        if u.get("ad") == urun_ad and str(u.get("gram")) == str(gram):
            return k
    return None

# Müşteri takip
def musteri_tamamlanan(uid):
    return musteriler.get(str(uid), {}).get("tamamlanan", 0)

def musteri_indirim_var_mi(uid):
    t = musteri_tamamlanan(uid)
    return t > 0 and t % INDIRIM_HER_N == 0

def musteri_kalan(uid):
    t = musteri_tamamlanan(uid)
    k = INDIRIM_HER_N - (t % INDIRIM_HER_N)
    return 0 if k == INDIRIM_HER_N else k

def indirimli_fiyat(f, uid):
    if musteri_indirim_var_mi(uid):
        return round(f * (1 - INDIRIM_ORANI / 100), 2)
    return f

def musteri_guncelle(uid, ad=""):
    k = str(uid)
    if k not in musteriler:
        musteriler[k] = {"tamamlanan": 0, "ad": ad}
    if ad:
        musteriler[k]["ad"] = ad
    musteriler[k]["tamamlanan"] += 1
    kaydet(M_DOSYA, musteriler)

# Giriş ekranı builder
def giris_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Alisverise Basla",  callback_data="giris_alisveris")],
        [InlineKeyboardButton("📋 Market Kurallari",   callback_data="giris_kurallar")],
        [InlineKeyboardButton("📢 Kanalimiz",          url=ayarlar.get("kanal_link", "https://t.me/kanaliniz"))],
        [InlineKeyboardButton("🆘 Destek",             url=ayarlar.get("destek_link", "https://t.me/destekkullanici"))],
    ])

def giris_metni(user):
    t     = musteri_tamamlanan(user.id)
    kalan = musteri_kalan(user.id)
    aktif = musteri_indirim_var_mi(user.id)
    if aktif:
        ind = f"🎉 Bu sipariste %{INDIRIM_ORANI} indirim hakkın var!"
    elif kalan > 0:
        ind = f"🎁 {kalan} siparis sonra %{INDIRIM_ORANI} indirim kazanacaksin!"
    else:
        ind = f"🎁 {INDIRIM_HER_N} siparis yap, %{INDIRIM_ORANI} indirim kazan!"
    return (
        f"👋 Merhaba, {user.first_name}!\n\n"
        f"🛒 Toplam Siparisiniz: {t}\n"
        f"{ind}\n\n"
        f"Asagidan devam edin:"
    )

# ─── GIRIŞ ───────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user = update.effective_user
    foto = ayarlar.get("giris_foto_id", "")
    if foto:
        await update.message.reply_photo(photo=foto, caption=giris_metni(user), reply_markup=giris_kb())
    else:
        await update.message.reply_text(giris_metni(user), reply_markup=giris_kb())

async def giris_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user = q.from_user
    has_photo = bool(q.message.photo)

    async def edit(txt, kb=None):
        if has_photo:
            await q.edit_message_caption(caption=txt, reply_markup=kb)
        else:
            await q.edit_message_text(txt, reply_markup=kb)

    if q.data == "giris_alisveris":
        context.user_data.clear()
        aktif = [il for il, ilceler in konumlar.items()
                 if any(ilce_konum_sayisi(il, ilce) > 0 for ilce in ilceler)]
        if not aktif:
            # Konum yoksa il listesini yine de göster
            iller = list(konumlar.keys())
            if not iller:
                await edit("Su an aktif bolge bulunmuyor.\nLutfen daha sonra tekrar deneyin.", 
                           InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Geri", callback_data="giris_geri")]]))
                return
            kb = [[InlineKeyboardButton(f"📍 {il}", callback_data=f"il:{il}")] for il in iller]
        else:
            kb = [[InlineKeyboardButton(f"📍 {il}", callback_data=f"il:{il}")] for il in aktif]
        kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="giris_geri")])
        try:
            await q.message.delete()
        except:
            pass
        await q.message.chat.send_message("Il secin:", reply_markup=InlineKeyboardMarkup(kb))

    elif q.data == "giris_kurallar":
        kural = ayarlar.get("market_kurali", "Henuz yazilmamis.")
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Geri", callback_data="giris_geri")]])
        await edit(f"📋 Market Kurallari\n\n{kural}", kb)

    elif q.data == "giris_geri":
        foto = ayarlar.get("giris_foto_id", "")
        if foto and not has_photo:
            await q.message.delete()
            await q.message.chat.send_photo(photo=foto, caption=giris_metni(user), reply_markup=giris_kb())
        else:
            await edit(giris_metni(user), giris_kb())

# ─── MÜŞTERİ AKIŞI ───────────────────────────────────────────────────────────
async def il_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    has_photo = bool(q.message.photo)

    async def edit(txt, kb):
        if has_photo:
            await q.edit_message_caption(caption=txt, reply_markup=kb)
        else:
            await q.edit_message_text(txt, reply_markup=kb)

    if q.data == "iptal":
        await edit("Iptal edildi.", None)
    if q.data == "giris_geri":
        await edit(giris_metni(q.from_user), giris_kb())
    il = q.data.split(":", 1)[1]
    context.user_data["il"] = il
    aktif_ilceler = [ilce for ilce in konumlar.get(il, {}) if ilce_konum_sayisi(il, ilce) > 0]
    if not aktif_ilceler:
        await edit(f"{il} ilinde aktif bolge yok.", None)
    kb = [[InlineKeyboardButton(f"📌 {ilce}", callback_data=f"ilce:{ilce}")] for ilce in aktif_ilceler]
    kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="giris_geri")])
    kb.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
    await edit(f"Il: {il}\n\nBolge secin:", InlineKeyboardMarkup(kb))

async def ilce_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "iptal":
        await q.edit_message_text("Iptal edildi.")
    if q.data == "geri_il":
        aktif = [il for il, ilceler in konumlar.items() if any(ilce_konum_sayisi(il, ilce) > 0 for ilce in ilceler)]
        kb = [[InlineKeyboardButton(f"📍 {il}", callback_data=f"il:{il}")] for il in aktif]
        kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="giris_geri")])
        kb.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
        await q.edit_message_text("Il secin:", reply_markup=InlineKeyboardMarkup(kb))
    ilce = q.data.split(":", 1)[1]
    il   = context.user_data["il"]
    context.user_data["ilce"] = ilce
    urunler = ilce_urunler(il, ilce)
    if not urunler:
        await q.edit_message_text(f"{ilce} bolgesinde urun bulunamadi.")
    kb = [[InlineKeyboardButton(ad, callback_data=f"urun:{ad}")] for ad in urunler.keys()]
    kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_il")])
    kb.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
    await q.edit_message_text(f"Il: {il}  |  Bolge: {ilce}\n\nUrun secin:", reply_markup=InlineKeyboardMarkup(kb))

async def urun_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "iptal":
        await q.edit_message_text("Iptal edildi.")
    if q.data == "geri_il":
        il = context.user_data["il"]
        aktif_ilceler = [ilce for ilce in konumlar.get(il, {}) if ilce_konum_sayisi(il, ilce) > 0]
        kb = [[InlineKeyboardButton(f"📌 {ilce}", callback_data=f"ilce:{ilce}")] for ilce in aktif_ilceler]
        kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_il")])
        kb.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
        await q.edit_message_text("Bolge secin:", reply_markup=InlineKeyboardMarkup(kb))
    urun_ad = q.data.split(":", 1)[1]
    il      = context.user_data["il"]
    ilce    = context.user_data["ilce"]
    context.user_data["urun_ad"] = urun_ad
    urunler = ilce_urunler(il, ilce)
    gramlar = urunler.get(urun_ad, {})
    kb = [[InlineKeyboardButton(f"{g}  —  {miktar_fiyat_str(f)}", callback_data=f"gram:{g}")] for g, f in gramlar.items()]
    kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_il")])
    kb.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
    await q.edit_message_text(f"Il: {il}  |  Bolge: {ilce}\nUrun: {urun_ad}\n\nMiktar secin:", reply_markup=InlineKeyboardMarkup(kb))

async def gram_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "iptal":
        await q.edit_message_text("Iptal edildi.")
    if q.data == "geri_ilce":
        il   = context.user_data["il"]
        ilce = context.user_data["ilce"]
        urunler = ilce_urunler(il, ilce)
        kb = [[InlineKeyboardButton(ad, callback_data=f"urun:{ad}")] for ad in urunler.keys()]
        kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_il")])
        kb.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
        await q.edit_message_text("Urun secin:", reply_markup=InlineKeyboardMarkup(kb))
    gram  = q.data.split(":", 1)[1]
    il    = context.user_data["il"]
    ilce  = context.user_data["ilce"]
    urun_ad = context.user_data["urun_ad"]
    urunler = ilce_urunler(il, ilce)
    fobj    = urunler.get(urun_ad, {}).get(gram, {})
    tl_f    = indirimli_fiyat(miktar_tl(fobj), q.from_user.id)
    usd_f   = indirimli_fiyat(miktar_usd(fobj), q.from_user.id)
    context.user_data["gram"]      = gram
    context.user_data["fiyat_tl"]  = tl_f
    context.user_data["fiyat_usd"] = usd_f
    no = sp_no(q.from_user.id)
    context.user_data["no"] = no
    uid = q.from_user.id
    aktif = musteri_indirim_var_mi(uid)
    kalan = musteri_kalan(uid)
    if aktif:
        ind_txt = f"🎉 %{INDIRIM_ORANI} INDIRIM UYGULANDL!\n"
    elif kalan > 0:
        ind_txt = f"🎁 {kalan} siparis sonra %{INDIRIM_ORANI} indirim!\n"
    else:
        ind_txt = ""
    ozet = (
        f"Siparis Ozeti\n─────────────────\n"
        f"Siparis No : {no}\n"
        f"Il         : {il}\n"
        f"Bolge      : {ilce}\n"
        f"Urun       : {urun_ad}\n"
        f"Miktar     : {gram}\n"
        f"─────────────────\n"
        f"IBAN Fiyati  : {fiyat_str(tl_f)} TL\n"
        f"TRC20 Fiyati : {fiyat_str(usd_f)} USD\n"
        f"─────────────────\n"
        f"{ind_txt}\n"
        f"Odeme yontemini secin:"
    )
    kb = [
        [InlineKeyboardButton("🏦 IBAN / Havale", callback_data="odeme_iban")],
        [InlineKeyboardButton("💎 TRC20 (USDT)",  callback_data="odeme_trc20")],
        [InlineKeyboardButton("⬅️ Geri",           callback_data="geri_odeme_sec")],
        [InlineKeyboardButton("❌ Iptal",           callback_data="iptal")],
    ]
    # Ürünün fotoğrafı varsa fotoğraflı gönder
    urun_foto = None
    for hid, hu in havuz.items():
        if isinstance(hu, dict) and hu.get("ad") == urun_ad and hu.get("foto_id"):
            urun_foto = hu["foto_id"]
            break

    if urun_foto:
        try:
            await q.message.delete()
        except:
            pass
        await q.message.chat.send_photo(
            photo=urun_foto,
            caption=ozet,
            reply_markup=InlineKeyboardMarkup(kb)
        )
    else:
        await q.edit_message_text(ozet, reply_markup=InlineKeyboardMarkup(kb))

async def odeme_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    async def edit(txt, kb=None):
        try:
            if q.message.photo:
                await q.edit_message_caption(caption=txt, reply_markup=kb)
            else:
                await q.edit_message_text(txt, reply_markup=kb)
        except Exception as e:
            logger.error(f"edit hatasi: {e}")

    if q.data == "iptal":
        no = context.user_data.get("no")
        if no and no in siparisler:
            il   = context.user_data.get("il")
            ilce = context.user_data.get("ilce")
            for km in konumlar.get(il, {}).get(ilce, []):
                if km.get("rezerve_no") == no:
                    km["rezerve"] = False
                    km.pop("rezerve_no", None)
                    break
            kaydet(K_DOSYA, konumlar)
            del siparisler[no]
            kaydet(S_DOSYA, siparisler)
        await edit("Iptal edildi.")
        return

    if q.data in ("geri_ilce", "geri_odeme_sec"):
        il      = context.user_data.get("il", "")
        ilce    = context.user_data.get("ilce", "")
        urun_ad = context.user_data.get("urun_ad", "")
        urunler = ilce_urunler(il, ilce)
        gramlar = urunler.get(urun_ad, {})
        kb = [[InlineKeyboardButton(f"{g}  —  {miktar_fiyat_str(f)}", callback_data=f"gram:{g}")] for g, f in gramlar.items()]
        kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_ilce")])
        kb.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
        try:
            await q.message.delete()
        except:
            pass
        await q.message.chat.send_message("Miktar secin:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if q.data in ("odeme_iban", "odeme_trc20"):
        context.user_data["odeme_yontemi"] = q.data
        no      = context.user_data.get("no", "?")
        urun_ad = context.user_data.get("urun_ad", "?")
        gram    = context.user_data.get("gram", "?")
        tl_f    = context.user_data.get("fiyat_tl", 0)
        usd_f   = context.user_data.get("fiyat_usd", 0)
        bilgi   = odeme_bilgileri.get("iban") if q.data == "odeme_iban" else odeme_bilgileri.get("trc20")
        fiyat_goster = f"{fiyat_str(tl_f)} TL" if q.data == "odeme_iban" else f"{fiyat_str(usd_f)} USD"
        context.user_data["fiyat"] = tl_f if q.data == "odeme_iban" else usd_f
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
        try:
            await q.message.delete()
        except:
            pass
        await q.message.chat.send_message(ozet, reply_markup=InlineKeyboardMarkup(kb))

async def odeme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    async def edit(txt, kb=None):
        if q.message.photo:
            await q.edit_message_caption(caption=txt, reply_markup=kb)
        else:
            await q.edit_message_text(txt, reply_markup=kb)

    if q.data == "iptal":
        await q.edit_message_text("Iptal edildi.")
    if q.data == "geri_odeme":
        il      = context.user_data["il"]
        ilce    = context.user_data["ilce"]
        urun_ad = context.user_data["urun_ad"]
        gram    = context.user_data["gram"]
        tl_f    = context.user_data["fiyat_tl"]
        usd_f   = context.user_data["fiyat_usd"]
        no      = context.user_data["no"]
        uid     = q.from_user.id
        kalan   = musteri_kalan(uid)
        aktif   = musteri_indirim_var_mi(uid)
        ind_txt = f"🎉 %{INDIRIM_ORANI} INDIRIM UYGULANDL!\n" if aktif else (f"🎁 {kalan} siparis sonra indirim!\n" if kalan > 0 else "")
        ozet = (
            f"Siparis Ozeti\n─────────────────\n"
            f"Siparis No : {no}\n"
            f"Il         : {il}\n"
            f"Bolge      : {ilce}\n"
            f"Urun       : {urun_ad}\n"
            f"Miktar     : {gram}\n"
            f"─────────────────\n"
            f"IBAN Fiyati  : {fiyat_str(tl_f)} TL\n"
            f"TRC20 Fiyati : {fiyat_str(usd_f)} USD\n"
            f"─────────────────\n{ind_txt}\nOdeme yontemini secin:"
        )
        kb = [
            [InlineKeyboardButton("🏦 IBAN / Havale", callback_data="odeme_iban")],
            [InlineKeyboardButton("💎 TRC20 (USDT)",  callback_data="odeme_trc20")],
            [InlineKeyboardButton("⬅️ Geri",           callback_data="geri_ilce")],
            [InlineKeyboardButton("❌ Iptal",           callback_data="iptal")],
        ]
        await q.edit_message_text(ozet, reply_markup=InlineKeyboardMarkup(kb))
    if q.data == "onayla":
        no = context.user_data.get("no", "?")
        siparisler[no] = {
            "user_id":    q.from_user.id,
            "musteri_ad": q.from_user.first_name or "",
            "il":         context.user_data["il"],
            "ilce":       context.user_data["ilce"],
            "urun":       f"{context.user_data['urun_ad']} {context.user_data['gram']}",
            "urun_ad":    context.user_data["urun_ad"],
            "gram":       context.user_data["gram"],
            "fiyat":      context.user_data["fiyat"],
            "odeme":      context.user_data.get("odeme_yontemi", ""),
            "durum":      "beklemede"
        }
        # Konumu rezerve et
        il      = siparisler[no]["il"]
        ilce    = siparisler[no]["ilce"]
        urun_ad = siparisler[no]["urun_ad"]
        gram    = siparisler[no]["gram"]
        rezerve_k = ilce_bos_konum_bul(il, ilce, urun_ad, gram)
        if rezerve_k:
            for km in konumlar.get(il, {}).get(ilce, []):
                if km["id"] == rezerve_k["id"]:
                    km["rezerve"]    = True
                    km["rezerve_no"] = no
                    break
            kaydet(K_DOSYA, konumlar)
        kaydet(S_DOSYA, siparisler)
        yontem = "Havale/EFT" if context.user_data.get("odeme_yontemi") == "odeme_iban" else "TRC20 (USDT)"
        await edit(
            f"Siparisıniz alindi!\n\nSiparis No: {no}\nOdeme: {yontem}\n\nDekontu gonderin."
        )

# ─── DEKONT ──────────────────────────────────────────────────────────────────
async def foto_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid == ADMIN_ID:
        if uid in adm and adm[uid].get("adim") == "giris_foto":
            ayarlar["giris_foto_id"] = update.message.photo[-1].file_id
            kaydet(A_DOSYA, ayarlar)
            del adm[uid]
            await update.message.reply_text("Giris gorseli ayarlandi!\n\n/start ile test edebilirsin.")
            return
        if uid in adm and adm[uid].get("adim") == "u_foto":
            hid = adm[uid].get("hid")
            if hid and isinstance(havuz.get(hid), dict):
                havuz[hid]["foto_id"] = update.message.photo[-1].file_id
                kaydet(H_DOSYA, havuz)
                del adm[uid]
                await update.message.reply_text(f"✅ Urun gorseli kaydedildi!")
            else:
                await update.message.reply_text("Hata: urun bulunamadi.")
            return
        if uid in adm and adm[uid].get("adim") == "foto":
            adm[uid]["foto_id"] = update.message.photo[-1].file_id
            adm[uid]["adim"]    = "konum"
            await update.message.reply_text("Fotograf kaydedildi!\n\nSimdi konumu gonder:")
            return
        await update.message.reply_text(f"Fotograf ID:\n{update.message.photo[-1].file_id}")
        return
    # Beklemede olan siparişi bul
    no = context.user_data.get("no")
    if no and (no not in siparisler or siparisler[no].get("durum") != "beklemede"):
        no = None
    if not no:
        for n, s in siparisler.items():
            if str(s["user_id"]) == str(uid) and s["durum"] == "beklemede":
                no = n
                break

    if not no or no not in siparisler:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛒 Siparis Olustur", url=f"https://t.me/{(await context.bot.get_me()).username}")]])
        await update.message.reply_text(
            "Aktif siparisıniz bulunmuyor.\nSiparis olusturmak icin /start yazin.",
        )
        return

    s = siparisler[no]

    # İki fotoğraf gelirse sadece müşteriye bilgi ver, admine tekrar gönderme
    if s.get("dekont_gonderildi"):
        await update.message.reply_text(
            f"Dekontunuz zaten alindi!\nSiparis No: {no}\n\nAdmin onayı bekleniyor."
        )
        return

    siparisler[no]["dekont_gonderildi"] = True
    kaydet(S_DOSYA, siparisler)

    kb = [[InlineKeyboardButton(f"✅ Onayla — {no}", callback_data=f"onay:{no}"),
           InlineKeyboardButton(f"❌ Reddet — {no}", callback_data=f"ret:{no}")]]
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=update.message.photo[-1].file_id,
        caption=(
            f"Yeni Dekont!\nNo: {no}\n"
            f"Il/Ilce: {s.get('il','?')}/{s.get('ilce','?')}\n"
            f"Urun: {s.get('urun','?')}\n"
            f"Fiyat: {fiyat_str(s.get('fiyat',0))}\n\nOnaylamak icin:"
        ),
        reply_markup=InlineKeyboardMarkup(kb)
    )
    await update.message.reply_text(f"Dekontunuz alindi! Siparis No: {no}")

# ─── KONUM ───────────────────────────────────────────────────────────────────
async def konum_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_ID:
        return
    if uid not in adm or adm[uid].get("adim") != "konum":
        await update.message.reply_text("Aktif konum ekleme islemi yok.")
        return
    islem = adm[uid]
    il    = islem["il"]
    ilce  = islem["ilce"]
    lat   = update.message.location.latitude
    lon   = update.message.location.longitude
    yeni  = {"id": k_id(), "lat": lat, "lon": lon, "foto_id": islem["foto_id"], "silindi": False, "urun": {}}
    if il not in konumlar: konumlar[il] = {}
    if ilce not in konumlar[il]: konumlar[il][ilce] = []
    konumlar[il][ilce].append(yeni)
    kaydet(K_DOSYA, konumlar)
    kidx = len(konumlar[il][ilce]) - 1
    adm[uid] = {"adim": "urun_sec", "il": il, "ilce": ilce, "kidx": kidx}
    kb = [[InlineKeyboardButton(u["ad"], callback_data=f"ks:{hid}:{il}:{ilce}:{kidx}")]
          for hid, u in havuz.items() if isinstance(u, dict)]
    await update.message.reply_text("Konum kaydedildi!\n\nUrunu sec:", reply_markup=InlineKeyboardMarkup(kb))

# ─── ADMİN CALLBACK ──────────────────────────────────────────────────────────
async def adm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("Yetkisiz!", show_alert=True)
        return
    await q.answer()
    d = q.data

    if d.startswith("ks:"):
        p    = d.split(":")
        hid  = p[1]; il = p[2]; ilce = p[3]; kidx = int(p[4])
        u    = havuz.get(hid, {})
        ad   = u.get("ad", "?")
        mik  = u.get("miktarlar", {})
        adm[ADMIN_ID] = {"adim": "gramaj_sec", "il": il, "ilce": ilce, "kidx": kidx, "urun_ad": ad, "hid": hid}
        kb   = [[InlineKeyboardButton(f"{g}  —  {miktar_fiyat_str(f)}", callback_data=f"ksg:{hid}:{g}:{il}:{ilce}:{kidx}")]
                for g, f in mik.items()]
        await q.edit_message_text(f"Urun: {ad}\n\nGramaji sec:", reply_markup=InlineKeyboardMarkup(kb))

    elif d.startswith("ksg:"):
        p    = d.split(":")
        hid  = p[1]; gram = p[2]; il = p[3]; ilce = p[4]; kidx = int(p[5])
        hu   = havuz.get(hid, {})
        ad   = hu.get("ad", "?")
        fobj = hu.get("miktarlar", {}).get(gram, {})
        konumlar[il][ilce][kidx]["urun"] = {"ad": ad, "gram": gram, "fiyat": fobj}
        kaydet(K_DOSYA, konumlar)
        if ADMIN_ID in adm: del adm[ADMIN_ID]
        kalan = ilce_konum_sayisi(il, ilce)
        kb = [
            [InlineKeyboardButton("📍 Ayni Ilceye Yeni Konum", callback_data=f"yeni_k:{il}:{ilce}")],
            [InlineKeyboardButton("✅ Tamamlandi",              callback_data="tamam")],
        ]
        await q.edit_message_text(
            f"Kaydedildi!\n{il}/{ilce} — {ad} {gram} — {miktar_fiyat_str(fobj)}\n\n{kalan} aktif konum var.",
            reply_markup=InlineKeyboardMarkup(kb)
        )

    elif d.startswith("yeni_k:"):
        p = d.split(":"); il = p[1]; ilce = p[2]
        adm[ADMIN_ID] = {"adim": "foto", "il": il, "ilce": ilce}
        await q.edit_message_text(f"{il}/{ilce} icin yeni konum.\n\nFotografi gonder:")

    elif d == "tamam":
        await q.edit_message_text("Tamamlandi! /konum_ekle ile yeni konum ekleyebilirsin.")

    elif d.startswith("ret:"):
        no = d.split(":")[1]
        s  = siparisler.get(no)
        if not s:
            await q.answer("Siparis bulunamadi!", show_alert=True)
            return
        if s["durum"] in ("tamamlandi",):
            await q.answer("Siparis zaten tamamlandi!", show_alert=True)
            return
        # Rezerveyi serbest bırak
        il   = s.get("il", "")
        ilce = s.get("ilce", "")
        for km in konumlar.get(il, {}).get(ilce, []):
            if km.get("rezerve_no") == no:
                km["rezerve"] = False
                km.pop("rezerve_no", None)
                break
        kaydet(K_DOSYA, konumlar)
        siparisler[no]["durum"] = "reddedildi"
        kaydet(S_DOSYA, siparisler)
        # Müşteriye bildirim
        mid = s["user_id"]
        red_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 Alisverise Basla", callback_data="giris_alisveris")],
            [InlineKeyboardButton("🆘 Destek", url=ayarlar.get("destek_link", "https://t.me/destekkullanici"))],
        ])
        await context.bot.send_message(
            chat_id=mid,
            text=(
                f"Siparisıniz reddedildi.\n\n"
                f"Siparis No: {no}\n\n"
                f"Detayli bilgi icin destek hattimizla iletisime gecebilirsiniz."
            ),
            reply_markup=red_kb
        )
        await q.edit_message_caption(f"Reddedildi! {no}")

    elif d.startswith("onay:"):
        no = d.split(":")[1]
        s  = siparisler.get(no)
        if not s:
            await q.edit_message_caption("Siparis bulunamadi.")
            return
        if s["durum"] in ("isleniyor", "tamamlandi"):
            await q.answer(f"Zaten {s['durum']}!", show_alert=True)
            return
        il = s["il"]; ilce = s["ilce"]
        # Önce bu siparişe rezerveli konumu bul
        k = None
        for km in konumlar.get(il, {}).get(ilce, []):
            if km.get("rezerve_no") == no and not km.get("silindi"):
                k = km
                break
        # Yoksa normal ara
        if not k:
            k = ilce_konum_bul(il, ilce, s["urun_ad"], s["gram"])
        if not k:
            await q.edit_message_caption(f"{il}/{ilce} icin musait konum yok!")
            return
        siparisler[no]["durum"] = "isleniyor"
        kaydet(S_DOSYA, siparisler)
        mid = s["user_id"]
        await context.bot.send_photo(chat_id=mid, photo=k["foto_id"],
            caption=f"Siparisıniz hazirlandi!\nNo: {no}\nAsagidaki konumdan teslim alin.")
        await context.bot.send_location(chat_id=mid, latitude=k["lat"], longitude=k["lon"])
        await context.bot.send_message(chat_id=mid, text=f"Teslimata hazir!\nNo: {no}\n\nIyi gunler!")
        for km in konumlar.get(il, {}).get(ilce, []):
            if km["id"] == k["id"]:
                km["silindi"]  = True
                km["rezerve"]  = False
                km.pop("rezerve_no", None)
                break
        kaydet(K_DOSYA, konumlar)
        siparisler[no]["durum"] = "tamamlandi"
        kaydet(S_DOSYA, siparisler)
        musteri_guncelle(mid, s.get("musteri_ad", ""))
        yeni_t    = musteri_tamamlanan(mid)
        yeni_k    = musteri_kalan(mid)
        if yeni_k == 0:
            await context.bot.send_message(chat_id=mid,
                text=f"Tebrikler! {yeni_t}. siparisini tamamladin!\nBir sonraki sipariste %{INDIRIM_ORANI} indirim kazandin!")
        elif yeni_k <= 2:
            await context.bot.send_message(chat_id=mid,
                text=f"%{INDIRIM_ORANI} indirim icin {yeni_k} siparisin kaldi!")
        kalan = ilce_konum_sayisi(il, ilce)
        uyari = f"\n\n{il}/{ilce}: {kalan} konum kaldi!" if kalan <= 3 else ""
        await q.edit_message_caption(f"Tamamlandi! {no} — {yeni_t}. siparis{uyari}")

# ─── ADMİN: /konum_ekle ──────────────────────────────────────────────────────
async def konum_ekle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    uid = update.effective_user.id
    if uid in adm: del adm[uid]
    iller = list(konumlar.keys())
    kb = [[InlineKeyboardButton(f"📍 {il}", callback_data=f"ke_il:{il}")] for il in iller]
    kb.append([InlineKeyboardButton("➕ Yeni Il", callback_data="ke_yeni_il")])
    await update.message.reply_text("Il sec:", reply_markup=InlineKeyboardMarkup(kb))

async def ke_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("Yetkisiz!", show_alert=True); return
    await q.answer()
    d = q.data
    if d == "ke_yeni_il":
        adm[ADMIN_ID] = {"adim": "yeni_il"}
        await q.edit_message_text("Yeni il adini yaz:")
    elif d.startswith("ke_il:"):
        il = d.split(":", 1)[1]
        ilceler = list(konumlar.get(il, {}).keys())
        kb = [[InlineKeyboardButton(f"📌 {ilce}", callback_data=f"ke_ilce:{il}:{ilce}")] for ilce in ilceler]
        kb.append([InlineKeyboardButton("➕ Yeni Ilce", callback_data=f"ke_yeni_ilce:{il}")])
        await q.edit_message_text(f"Il: {il}\n\nIlce sec:", reply_markup=InlineKeyboardMarkup(kb))
    elif d.startswith("ke_yeni_ilce:"):
        il = d.split(":", 1)[1]
        adm[ADMIN_ID] = {"adim": "yeni_ilce", "il": il}
        await q.edit_message_text(f"{il} icin ilce adini yaz:")
    elif d.startswith("ke_ilce:"):
        p = d.split(":"); il = p[1]; ilce = p[2]
        adm[ADMIN_ID] = {"adim": "foto", "il": il, "ilce": ilce}
        await q.edit_message_text(f"{il}/{ilce}\n\nFotografi gonder:")
    elif d.startswith("yeni_k:"):
        p = d.split(":"); il = p[1]; ilce = p[2]
        adm[ADMIN_ID] = {"adim": "foto", "il": il, "ilce": ilce}
        await q.edit_message_text(f"{il}/{ilce} icin yeni konum.\n\nFotografi gonder:")

# ─── ADMİN: /urunler ─────────────────────────────────────────────────────────
async def goster_havuz(hedef):
    msg = "Urun Havuzu\n─────────────────\n"
    for hid, u in havuz.items():
        ad  = u["ad"] if isinstance(u, dict) else u
        tip = u.get("tip", "gram") if isinstance(u, dict) else "gram"
        mik = u.get("miktarlar", {}) if isinstance(u, dict) else {}
        mik_txt = "  ".join([f"{m}: {miktar_fiyat_str(f)}" for m, f in mik.items()]) if mik else "Miktar yok"
        msg += f"\n{ad} [{tip_label(tip)}]\n  {mik_txt}\n"
    msg += "\nDuzenlemek icin secin:"
    kb = [[InlineKeyboardButton(u["ad"] if isinstance(u, dict) else u, callback_data=f"u_detay:{hid}")]
          for hid, u in havuz.items()]
    kb.append([InlineKeyboardButton("➕ Yeni Urun Ekle", callback_data="u_ekle")])
    markup = InlineKeyboardMarkup(kb)
    if hasattr(hedef, "reply_text"):
        await hedef.reply_text(msg, reply_markup=markup)
    else:
        await hedef.edit_message_text(msg, reply_markup=markup)

async def urunler_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    uid = update.effective_user.id
    if uid in adm: del adm[uid]  # Önceki yarım işlemi temizle
    await goster_havuz(update.message)

async def urun_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("Yetkisiz!", show_alert=True); return
    await q.answer()
    d = q.data

    if d == "u_ekle":
        adm[ADMIN_ID] = {"adim": "u_ad"}
        await q.edit_message_text("Yeni urun adini yaz:")

    elif d.startswith("u_tip_"):
        tip = d.replace("u_tip_", "")
        adm[ADMIN_ID]["tip"]  = tip
        adm[ADMIN_ID]["adim"] = "u_miktar"
        ad = adm[ADMIN_ID].get("urun_ad", "?")
        ipucu = {"gram": "örn: 1g, 3.5g", "tekli": "örn: 1 Adet", "kutu": "örn: 1 Kutu"}.get(tip, "")
        await q.edit_message_text(f"Urun: {ad} [{tip_label(tip)}]\n\nMiktar yaz ({ipucu}):")

    elif d.startswith("u_detay:"):
        hid = d.split(":")[1]
        u   = havuz.get(hid, {})
        ad  = u["ad"] if isinstance(u, dict) else u
        tip = u.get("tip", "gram") if isinstance(u, dict) else "gram"
        mik = u.get("miktarlar", {}) if isinstance(u, dict) else {}
        mik_txt = "\n".join([f"  {m}: {miktar_fiyat_str(f)}" for m, f in mik.items()]) or "  Miktar yok"
        foto_durum = "✅ Foto var" if u.get("foto_id") else "❌ Foto yok"
        kb = [
            [InlineKeyboardButton(f"🖼 Fotograf Ekle/Degistir ({foto_durum})", callback_data=f"u_foto:{hid}")],
            [InlineKeyboardButton("➕ Miktar/Fiyat Ekle", callback_data=f"u_mik_ekle:{hid}")],
            [InlineKeyboardButton("➖ Miktar Sil",        callback_data=f"u_mik_sil:{hid}")],
            [InlineKeyboardButton("🗑 Urunu Sil",         callback_data=f"u_sil:{hid}")],
            [InlineKeyboardButton("⬅️ Geri",              callback_data="u_geri")],
        ]
        await q.edit_message_text(
            f"{ad} [{tip_label(tip)}]\n\n{mik_txt}\n\nNe yapmak istiyorsun?",
            reply_markup=InlineKeyboardMarkup(kb)
        )

    elif d == "u_geri":
        await goster_havuz(q)

    elif d.startswith("u_mik_ekle:"):
        hid = d.split(":")[1]
        u   = havuz.get(hid, {})
        tip = u.get("tip", "gram") if isinstance(u, dict) else "gram"
        ipucu = {"gram": "örn: 7g", "tekli": "örn: 10 Adet", "kutu": "örn: 3 Kutu"}.get(tip, "")
        adm[ADMIN_ID] = {"adim": "u_miktar", "hid": hid, "yeni": False}
        await q.edit_message_text(f"Eklenecek miktari yaz ({ipucu}):")

    elif d.startswith("u_mik_sil:"):
        hid = d.split(":")[1]
        u   = havuz.get(hid, {})
        mik = u.get("miktarlar", {}) if isinstance(u, dict) else {}
        if not mik:
            await q.answer("Silinecek miktar yok!", show_alert=True); return
        kb = [[InlineKeyboardButton(f"🗑 {m} — {miktar_fiyat_str(f)}", callback_data=f"u_mik_sil2:{hid}:{m}")]
              for m, f in mik.items()]
        kb.append([InlineKeyboardButton("⬅️ Geri", callback_data=f"u_detay:{hid}")])
        await q.edit_message_text("Hangi miktari silmek istiyorsun?", reply_markup=InlineKeyboardMarkup(kb))

    elif d.startswith("u_mik_sil2:"):
        p = d.split(":"); hid = p[1]; mik_ad = p[2]
        u = havuz.get(hid, {})
        if isinstance(u, dict) and mik_ad in u.get("miktarlar", {}):
            del u["miktarlar"][mik_ad]
            kaydet(H_DOSYA, havuz)
        await q.edit_message_text(f"'{mik_ad}' silindi!")

    elif d.startswith("u_foto:"):
        hid = d.split(":")[1]
        adm[ADMIN_ID] = {"adim": "u_foto", "hid": hid}
        await q.edit_message_text("Urun fotografini gonder:")

    elif d.startswith("u_sil:"):
        hid = d.split(":")[1]
        u   = havuz.pop(hid, {})
        ad  = u["ad"] if isinstance(u, dict) else u
        kaydet(H_DOSYA, havuz)
        await q.edit_message_text(f"'{ad}' silindi!")

    elif d == "u_gramaj_devam":
        islem = adm.get(ADMIN_ID, {})
        tip   = islem.get("tip", "gram")
        adm[ADMIN_ID]["adim"] = "u_miktar"
        ipucu = {"gram": "örn: 7g", "tekli": "örn: 10 Adet", "kutu": "örn: 3 Kutu"}.get(tip, "")
        await q.edit_message_text(f"Yeni miktari yaz ({ipucu}):")

    elif d == "u_gorsel_ekle":
        # Önce kaydet, sonra fotoğraf iste
        islem     = adm.get(ADMIN_ID, {})
        ad        = islem.get("urun_ad", "")
        hid       = islem.get("hid", f"h{int(time.time())}")
        tip       = islem.get("tip", "gram")
        miktarlar = islem.get("miktarlar", {})
        havuz[hid] = {"ad": ad, "tip": tip, "miktarlar": miktarlar, "foto_id": ""}
        kaydet(H_DOSYA, havuz)
        adm[ADMIN_ID] = {"adim": "u_foto", "hid": hid}
        await q.edit_message_text(f"'{ad}' kaydedildi!\n\nSimdi urun fotografini gonder:")

    elif d == "u_gramaj_kaydet":
        islem    = adm.get(ADMIN_ID, {})
        ad       = islem.get("urun_ad", "")
        hid      = islem.get("hid", f"h{int(time.time())}")
        tip      = islem.get("tip", "gram")
        miktarlar = islem.get("miktarlar", {})
        havuz[hid] = {"ad": ad, "tip": tip, "miktarlar": miktarlar}
        kaydet(H_DOSYA, havuz)
        if ADMIN_ID in adm: del adm[ADMIN_ID]
        mik_txt = "  ".join([f"{m}: {miktar_fiyat_str(f)}" for m, f in miktarlar.items()])
        await q.edit_message_text(f"'{ad}' [{tip_label(tip)}] eklendi!\n\n{mik_txt}")

# ─── ADMİN: /ayarlar ─────────────────────────────────────────────────────────
async def ayarlar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    uid = update.effective_user.id
    if uid in adm: del adm[uid]
    await goster_ayarlar(update.message)

async def goster_ayarlar(hedef):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🖼 Giris Gorseli",      callback_data="ay_foto")],
        [InlineKeyboardButton("📢 Kanal Linki",         callback_data="ay_kanal")],
        [InlineKeyboardButton("🆘 Destek Linki",        callback_data="ay_destek")],
        [InlineKeyboardButton("📋 Market Kurallari",    callback_data="ay_kurallar")],
    ])
    txt = (
        f"Bot Ayarlari\n─────────────────\n\n"
        f"Giris Gorseli : {'Ayarli ✅' if ayarlar.get('giris_foto_id') else 'Ayarlanmamis ❌'}\n"
        f"Kanal Link    : {ayarlar.get('kanal_link', '-')}\n"
        f"Destek Link   : {ayarlar.get('destek_link', '-')}\n"
        f"Market Kurali : {'Ayarli ✅' if ayarlar.get('market_kurali') else 'Bos ❌'}\n"
    )
    if hasattr(hedef, "reply_text"):
        await hedef.reply_text(txt, reply_markup=kb)
    else:
        await hedef.edit_message_text(txt, reply_markup=kb)

async def ayarlar_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("Yetkisiz!", show_alert=True); return
    await q.answer()
    d = q.data

    if d == "ay_foto":
        adm[ADMIN_ID] = {"adim": "giris_foto"}
        await q.edit_message_text("Giris icin gorsel gonder:")

    elif d == "ay_kanal":
        adm[ADMIN_ID] = {"adim": "ay_kanal"}
        await q.edit_message_text(
            f"Mevcut kanal linki:\n{ayarlar.get('kanal_link', '-')}\n\nYeni linki yaz:"
        )

    elif d == "ay_destek":
        adm[ADMIN_ID] = {"adim": "ay_destek"}
        await q.edit_message_text(
            f"Mevcut destek linki:\n{ayarlar.get('destek_link', '-')}\n\nYeni linki yaz:"
        )

    elif d == "ay_kurallar":
        adm[ADMIN_ID] = {"adim": "ay_kurallar"}
        await q.edit_message_text("Yeni market kurallarini yaz:")

    elif d == "ay_geri":
        await goster_ayarlar(q)

# ─── ADMİN: /odeme ───────────────────────────────────────────────────────────
async def odeme_yonetim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏦 IBAN Duzenle",  callback_data="ody_iban")],
        [InlineKeyboardButton("💎 TRC20 Duzenle", callback_data="ody_trc20")],
    ])
    await update.message.reply_text(
        f"Odeme Bilgileri\n─────────────────\n\nIBAN:\n{odeme_bilgileri.get('iban','')}\n\n"
        f"─────────────\n\nTRC20:\n{odeme_bilgileri.get('trc20','')}\n\nDuzenlemek icin sec:",
        reply_markup=kb
    )

async def odeme_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("Yetkisiz!", show_alert=True); return
    await q.answer()
    if q.data == "ody_iban":
        adm[ADMIN_ID] = {"adim": "iban_guncelle"}
        await q.edit_message_text("Yeni IBAN bilgilerini yaz:")
    elif q.data == "ody_trc20":
        adm[ADMIN_ID] = {"adim": "trc20_guncelle"}
        await q.edit_message_text("Yeni TRC20 adresini yaz:")

# ─── METİN ───────────────────────────────────────────────────────────────────
async def metin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = update.message.text.strip()

    if uid == ADMIN_ID and uid in adm:
        a = adm[uid]

        if a["adim"] == "yeni_il":
            if txt not in konumlar: konumlar[txt] = {}; kaydet(K_DOSYA, konumlar)
            # adm'ı silme, ilçe seçimine yönlendir
            adm[uid] = {"adim": "il_secildi", "il": txt}
            ilceler = list(konumlar.get(txt, {}).keys())
            kb = [[InlineKeyboardButton(f"📌 {ilce}", callback_data=f"ke_ilce:{txt}:{ilce}")] for ilce in ilceler]
            kb.append([InlineKeyboardButton("➕ Yeni Ilce", callback_data=f"ke_yeni_ilce:{txt}")])
            await update.message.reply_text(f"'{txt}' eklendi!\n\nIlce sec:", reply_markup=InlineKeyboardMarkup(kb))
            return

        elif a["adim"] == "yeni_ilce":
            il = a["il"]
            if il not in konumlar: konumlar[il] = {}
            if txt not in konumlar[il]: konumlar[il][txt] = []; kaydet(K_DOSYA, konumlar)
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
            a["gecici_miktar"] = txt
            a["adim"]          = "u_fiyat_tl"
            await update.message.reply_text(f"'{txt}' icin TL fiyatini yaz:")
            return

        elif a["adim"] == "u_fiyat_tl":
            try:
                tl = float(txt.replace(",", "."))
                a["gecici_tl"] = tl
                a["adim"]      = "u_fiyat_usd"
                await update.message.reply_text(f"'{a['gecici_miktar']}' icin Dolar (USD) fiyatini yaz:")
            except:
                await update.message.reply_text("Gecersiz! Sayi gir (örn: 450)")
            return

        elif a["adim"] == "u_fiyat_usd":
            try:
                usd  = float(txt.replace(",", "."))
                tl   = a.get("gecici_tl", 0)
                m    = a.get("gecici_miktar", "?")
                fobj = {"tl": tl, "usd": usd}
                if a.get("yeni"):
                    a["miktarlar"][m] = fobj
                    a["adim"] = "u_devam"
                    mik_txt = "  ".join([f"{mk}: {miktar_fiyat_str(fv)}" for mk, fv in a["miktarlar"].items()])
                    kb = [
                        [InlineKeyboardButton("➕ Baska Miktar Ekle", callback_data="u_gramaj_devam")],
                        [InlineKeyboardButton("✅ Kaydet (Gorselsiz)", callback_data="u_gramaj_kaydet")],
                        [InlineKeyboardButton("🖼 Gorsel Ekle ve Kaydet", callback_data="u_gorsel_ekle")],
                    ]
                    await update.message.reply_text(f"Eklendi!\n\n{mik_txt}", reply_markup=InlineKeyboardMarkup(kb))
                else:
                    hid = a["hid"]
                    if isinstance(havuz.get(hid), dict):
                        havuz[hid]["miktarlar"][m] = fobj
                        kaydet(H_DOSYA, havuz)
                    del adm[uid]
                    await update.message.reply_text(f"'{m}: {miktar_fiyat_str(fobj)}' eklendi!")
            except:
                await update.message.reply_text("Gecersiz! Sayi gir (örn: 14)")
            return

        elif a["adim"] == "ay_kanal":
            ayarlar["kanal_link"] = txt
            kaydet(A_DOSYA, ayarlar)
            del adm[uid]
            await update.message.reply_text(f"Kanal linki guncellendi!\n{txt}")
            return

        elif a["adim"] == "ay_destek":
            ayarlar["destek_link"] = txt
            kaydet(A_DOSYA, ayarlar)
            del adm[uid]
            await update.message.reply_text(f"Destek linki guncellendi!\n{txt}")
            return

        elif a["adim"] == "ay_kurallar":
            ayarlar["market_kurali"] = txt
            kaydet(A_DOSYA, ayarlar)
            del adm[uid]
            await update.message.reply_text("Market kurallari guncellendi!")
            return

        elif a["adim"] == "iban_guncelle":
            odeme_bilgileri["iban"] = "Odeme Yontemi: IBAN / Havale\n─────────────────\n" + txt
            kaydet(O_DOSYA, odeme_bilgileri)
            del adm[uid]
            await update.message.reply_text("IBAN guncellendi!")
            return

        elif a["adim"] == "trc20_guncelle":
            odeme_bilgileri["trc20"] = "Odeme Yontemi: TRC20 (USDT)\n─────────────────\nAdres: " + txt + "\n\nGondermeden once adresi kontrol edin!"
            kaydet(O_DOSYA, odeme_bilgileri)
            del adm[uid]
            await update.message.reply_text("TRC20 guncellendi!")
            return

    await update.message.reply_text("Siparis vermek icin /start yazin.")

# ─── KOMUTLAR ────────────────────────────────────────────────────────────────
async def konumlar_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not konumlar:
        await update.message.reply_text("Hic konum yok.")
        return
    for il, ilceler in konumlar.items():
        for ilce, liste in ilceler.items():
            kalan = ilce_konum_sayisi(il, ilce)
            e   = "🟢" if kalan > 3 else ("🟡" if kalan > 0 else "🔴")
            rezerveli = sum(1 for k in liste if k.get("rezerve") and not k.get("silindi"))
            bos       = kalan - rezerveli
            msg = f"{e} {il}/{ilce} — {bos} bos / {rezerveli} rezerveli / {len(liste)} toplam\n─────────────────"
            n   = 0
            for k in liste:
                if k.get("silindi"): continue
                n += 1
                u    = k.get("urun", {})
                rzv  = " 🔒 REZERVE" if k.get("rezerve") else ""
                msg += f"\n#{n}  {u.get('ad','?')} {u.get('gram','?')} — {miktar_fiyat_str(u.get('fiyat',{}))}  {rzv}\n  📍 {k.get('lat',0):.4f}, {k.get('lon',0):.4f}"
            if n == 0:
                msg += "\n\nAktif konum yok."
            await update.message.reply_text(msg)

async def siparisler_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not siparisler:
        await update.message.reply_text("Henuz siparis yok.")
        return
    e   = {"beklemede": "⏳", "isleniyor": "🔄", "tamamlandi": "✅"}
    msg = "Siparisler\n─────────────────\n"
    for no, s in siparisler.items():
        msg += f"\n{e.get(s['durum'],'?')} {no}\n  {s.get('il','')}/{s.get('ilce','')} | {s['urun']} | {fiyat_str(s['fiyat'])}\n"
    await update.message.reply_text(msg)

async def musteriler_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not musteriler:
        await update.message.reply_text("Henuz musteri yok.")
        return
    msg = "Musteri Listesi\n─────────────────\n"
    for uid, m in sorted(musteriler.items(), key=lambda x: -x[1].get("tamamlanan", 0)):
        t     = m.get("tamamlanan", 0)
        ad    = m.get("ad", "?")
        kalan = musteri_kalan(int(uid))
        durum = "🎉 INDIRIM HAKKI VAR!" if t > 0 and t % INDIRIM_HER_N == 0 else f"{kalan} siparis kaldi"
        msg  += f"\n👤 {ad}\n  Tamamlanan: {t} | {durum}\n"
    await update.message.reply_text(msg)

async def gunsonu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    toplam = tamamlanan = bekleyen = 0
    gelir_tl = gelir_usd = 0.0
    iban_adet = trc20_adet = 0
    urun_sayac = {}
    for no, s in siparisler.items():
        toplam += 1
        if s["durum"] == "tamamlandi":
            tamamlanan += 1
            f = float(s.get("fiyat", 0))
            odeme = s.get("odeme", "")
            if odeme == "odeme_iban":
                gelir_tl += f; iban_adet += 1
            else:
                gelir_usd += f; trc20_adet += 1
            u = s.get("urun", "?")
            urun_sayac[u] = urun_sayac.get(u, 0) + 1
        elif s["durum"] == "beklemede":
            bekleyen += 1
    toplam_k = kalan_k = kullanilan_k = 0
    k_satirlar = []
    for il, ilceler in konumlar.items():
        for ilce, liste in ilceler.items():
            for k in liste:
                toplam_k += 1
                if k.get("silindi"): kullanilan_k += 1
                else: kalan_k += 1
            aktif = ilce_konum_sayisi(il, ilce)
            e = "🟢" if aktif > 3 else ("🟡" if aktif > 0 else "🔴")
            k_satirlar.append(f"  {e} {il}/{ilce}: {aktif} kalan")
    rapor  = f"📊 GUN SONU — {time.strftime('%d.%m.%Y %H:%M')}\n═══════════════\n\n"
    rapor += f"📦 Siparis: {toplam} toplam | {tamamlanan} tamamlandi | {bekleyen} bekliyor\n\n"
    rapor += f"💰 Gelir:\n  IBAN: {fiyat_str(gelir_tl)} TL ({iban_adet})\n  TRC20: {fiyat_str(gelir_usd)} USD ({trc20_adet})\n\n"
    rapor += "🍬 Satislar:\n" + "\n".join([f"  {u}: {a}" for u, a in urun_sayac.items()]) + "\n\n" if urun_sayac else "🍬 Satis yok\n\n"
    rapor += f"📍 Konum: {kalan_k} kalan / {kullanilan_k} kullanildi\n" + "\n".join(k_satirlar)
    kb = [[InlineKeyboardButton("🗑 Siparisleri Sifirla", callback_data="gunsonu_sifirla")]]
    await update.message.reply_text(rapor, reply_markup=InlineKeyboardMarkup(kb))

async def gunsonu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("Yetkisiz!", show_alert=True); return
    await q.answer()
    if q.data == "gunsonu_sifirla":
        kb = [[InlineKeyboardButton("✅ Evet", callback_data="gunsonu_evet")],
              [InlineKeyboardButton("❌ Iptal", callback_data="gunsonu_iptal")]]
        await q.edit_message_text("Emin misin?\n\nTum siparisler silinecek.", reply_markup=InlineKeyboardMarkup(kb))
    elif q.data == "gunsonu_evet":
        siparisler.clear(); kaydet(S_DOSYA, siparisler)
        await q.edit_message_text(f"Siparisler sifirland! {time.strftime('%d.%m.%Y %H:%M')}")
    elif q.data == "gunsonu_iptal":
        await q.edit_message_text("Iptal edildi.")

async def iptal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Iptal edildi. /start ile baslayin.")

# ─── MAIN ────────────────────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Komutlar
    app.add_handler(CommandHandler("start",       start))
    app.add_handler(CommandHandler("siparisler",  siparisler_goster))
    app.add_handler(CommandHandler("konumlar",    konumlar_goster))
    app.add_handler(CommandHandler("konum_ekle",  konum_ekle))
    app.add_handler(CommandHandler("urunler",     urunler_goster))
    app.add_handler(CommandHandler("odeme",       odeme_yonetim))
    app.add_handler(CommandHandler("gunsonu",     gunsonu))
    app.add_handler(CommandHandler("musteriler",  musteriler_goster))
    app.add_handler(CommandHandler("ayarlar",     ayarlar_menu))
    app.add_handler(CommandHandler("iptal",       iptal))

    # Callback handlers - sıra önemli, önce özel pattern'ler
    app.add_handler(CallbackQueryHandler(giris_cb,  pattern=r"^giris_"))
    app.add_handler(CallbackQueryHandler(il_sec,    pattern=r"^il:"))
    app.add_handler(CallbackQueryHandler(ilce_sec,  pattern=r"^(ilce:|geri_il)"))
    app.add_handler(CallbackQueryHandler(urun_sec,  pattern=r"^(urun:)"))
    app.add_handler(CallbackQueryHandler(gram_sec,  pattern=r"^gram:"))
    app.add_handler(CallbackQueryHandler(odeme_sec, pattern=r"^(odeme_iban|odeme_trc20|geri_ilce|geri_odeme_sec)"))
    app.add_handler(CallbackQueryHandler(odeme,     pattern=r"^(onayla|geri_odeme|iptal)"))

    app.add_handler(CallbackQueryHandler(adm_cb,     pattern=r"^(ks:|ksg:|yeni_k:|tamam$|onay:|ret:)"))
    app.add_handler(CallbackQueryHandler(ke_cb,      pattern=r"^ke_"))
    app.add_handler(CallbackQueryHandler(urun_cb,    pattern=r"^u_"))
    app.add_handler(CallbackQueryHandler(odeme_cb,   pattern=r"^ody_"))
    app.add_handler(CallbackQueryHandler(ayarlar_cb, pattern=r"^ay_"))
    app.add_handler(CallbackQueryHandler(gunsonu_cb, pattern=r"^gunsonu_"))

    # Mesaj handlers
    app.add_handler(MessageHandler(filters.PHOTO,    foto_al))
    app.add_handler(MessageHandler(filters.LOCATION, konum_al))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, metin))

    logger.info("Bot basladi.")
    app.run_polling()

if __name__ == "__main__":
    main()
