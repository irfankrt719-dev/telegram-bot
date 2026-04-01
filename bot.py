"""
Telegram Sipariş Botu - Temiz Versiyon
"""
import logging, json, os, time, random, string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters, ConversationHandler
)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "BURAYA_TOKEN")
ADMIN_ID  = int(os.environ.get("ADMIN_ID", "123456789"))

# Admin dosyası
ADM_DOSYA = "adminler.json"
C_DOSYA   = "ciro.json"
KOD_DOSYA = "kodlar.json"

def adminler_yukle():
    if os.path.exists(ADM_DOSYA):
        try:
            with open(ADM_DOSYA, encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    # Varsayılan: sadece süper admin
    return {str(ADMIN_ID): {"seviye": "super", "ad": "Super Admin"}}

def adminler_kaydet():
    with open(ADM_DOSYA, "w", encoding="utf-8") as f:
        json.dump(adminler, f, ensure_ascii=False, indent=2)

IL, ILCE, URUN, GRAM, ODEME_SEC, ODEME = range(6)
adm = {}

S_DOSYA = "siparisler.json"
K_DOSYA = "konumlar.json"
H_DOSYA = "havuz.json"
O_DOSYA = "ödeme.json"
M_DOSYA = "musteriler.json"
A_DOSYA = "ayarlar.json"

HAVUZ_VARSAYILAN = {
    "h1": {"ad": "Deneme 1", "tip": "gram",  "miktarlar": {"2.5": {"tl": 4000.0, "usd": 80.0}, "5": {"tl": 7000.0, "usd": 150.0}}},
    "h2": {"ad": "Deneme 2", "tip": "tekli", "miktarlar": {"Jilet": {"tl": 2000.0, "usd": 40.0}, "Kutu": {"tl": 7000.0, "usd": 150.0}}}
}
ODEME_VARSAYILAN = {
    "iban":  "Ödeme Yontemi: IBAN / Havale\n─────────────────\nBanka: Ziraat Bankasi\nHesap Adi: Sirket Adi\nIBAN: TR00 0000 0000 0000 0000 0000 00\n\nAçıklama kismina sipariş numaranizi yazin!",
    "trc20": "Ödeme Yontemi: TRC20 (USDT)\n─────────────────\nAdres: BURAYA_TRC20_ADRESINIZI_YAZIN\n\nGöndermeden önce adresi kontrol edin!"
}
AYARLAR_VARSAYILAN = {
    "giris_foto_id": "",
    "kanal_link":    "https://t.me/kanaliniz",
    "destek_link":   "https://t.me/destekkullanici",
    "market_kurali": "Market kurallari henuz yazilmamis."
}

INDIRIM_HER_N = 5
INDIRIM_ORANI = 10

bot_aktif = True  # /on ve /off ile değişir

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

adminler        = adminler_yukle()
kodlar          = yukle(KOD_DOSYA, {})
ciro            = yukle(C_DOSYA, {"toplam_tl": 0, "toplam_usd": 0, "gunler": []})
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


def kod_uret(n=6):
    """n haneli benzersiz büyük harf+rakam kodu üret"""
    while True:
        kod = ''.join(random.choices(string.ascii_uppercase + string.digits, k=n))
        if kod not in kodlar:
            return kod

def musteri_kayitli_mi(uid):
    return musteriler.get(str(uid), {}).get("kayitli", False)

def musteri_kaydet_kod(uid, ad, kod):
    k = str(uid)
    if k not in musteriler:
        musteriler[k] = {"tamamlanan": 0, "ad": ad}
    musteriler[k]["kayitli"] = True
    musteriler[k]["ad"] = ad
    kaydet(M_DOSYA, musteriler)
    # Kodu kullanıldı işaretle
    if kod in kodlar:
        kodlar[kod]["kullanildi"] = True
        kodlar[kod]["kullanan"]   = uid
        kaydet(KOD_DOSYA, kodlar)

# Giriş ekranı builder
def giris_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Alışverişe Başla",  callback_data="giris_alisveris")],
        [InlineKeyboardButton("📋 Market Kuralları",   callback_data="giris_kurallar")],
        [InlineKeyboardButton("📢 Kanalımız",          url=ayarlar.get("kanal_link", "https://t.me/kanaliniz"))],
        [InlineKeyboardButton("🆘 Destek",             url=ayarlar.get("destek_link", "https://t.me/destekkullanici"))],
    ])

def giris_metni(user):
    t     = musteri_tamamlanan(user.id)
    kalan = musteri_kalan(user.id)
    aktif = musteri_indirim_var_mi(user.id)
    if aktif:
        ind = f"🎉 Bu siparişte %{INDIRIM_ORANI} indirim hakkın var!"
    elif kalan > 0:
        ind = f"🎁 {kalan} sipariş sonra %{INDIRIM_ORANI} indirim kazanacaksin!"
    else:
        ind = f"🎁 {INDIRIM_HER_N} sipariş yap, %{INDIRIM_ORANI} indirim kazan!"
    return (
        f"👋 Merhaba, {user.first_name}!\n\n"
        f"🛒 Toplam Siparişiniz: {t}\n"
        f"{ind}\n\n"
        f"Aşağıdan devam edin:"
    )

# ─── GIRIŞ ───────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user = update.effective_user
    uid  = user.id

    # Admin ise aktiflik kontrolü yok
    if is_saha(uid):
        foto = ayarlar.get("giris_foto_id", "")
        if foto:
            await update.message.reply_photo(photo=foto, caption=giris_metni(user), reply_markup=giris_kb())
        else:
            await update.message.reply_text(giris_metni(user), reply_markup=giris_kb())
        return

    # Bot kapalıysa hizmet dışı mesajı
    if not bot_aktif:
        await update.message.reply_text(
            "🚫 Hizmet Dışı\n\n"
            "Şu an hizmet vermiyoruz.\n"
            "Lütfen daha sonra tekrar deneyin.\n\n"
            f"Destek: {ayarlar.get('destek_link', '')}"
        )
        return

    # Kayıtlı müşteri ise direkt giriş
    if musteri_kayitli_mi(uid):
        foto = ayarlar.get("giris_foto_id", "")
        if foto:
            await update.message.reply_photo(photo=foto, caption=giris_metni(user), reply_markup=giris_kb())
        else:
            await update.message.reply_text(giris_metni(user), reply_markup=giris_kb())
        return

    # Kayıtlı değil - referans kodu sor
    context.user_data["bekleyen_kod"] = True
    await update.message.reply_text(
        "Hoşgeldiniz!\n\n"
        "Sisteme giriş yapabilmek icin referans kodunuzu girin:\n\n"
        "(Kod almak için yetkili kişiyle iletişime geçin)"
    )

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
        if not bot_aktif and not is_saha(q.from_user.id):
            await q.answer("Şu an hizmet dışıyız!", show_alert=True)
            return
        aktif = [il for il, ilceler in konumlar.items()
                 if any(ilce_konum_sayisi(il, ilce) > 0 for ilce in ilceler)]
        if not aktif:
            # Konum yoksa il listesini yine de göster
            iller = list(konumlar.keys())
            if not iller:
                await edit("Su an aktif bölge bulunmuyor.\nLütfen daha sonra tekrar deneyin.", 
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
        await q.message.chat.send_message("Il seçin:", reply_markup=InlineKeyboardMarkup(kb))

    elif q.data == "giris_kurallar":
        kural = ayarlar.get("market_kurali", "Henuz yazilmamis.")
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Geri", callback_data="giris_geri")]])
        await edit(f"📋 Market Kuralları\n\n{kural}", kb)

    elif q.data == "giris_geri":
        foto = ayarlar.get("giris_foto_id", "")
        if foto and not has_photo:
            await q.message.delete()
            await q.message.chat.send_photo(photo=foto, caption=giris_metni(user), reply_markup=giris_kb())
        else:
            await edit(giris_metni(user), giris_kb())


# ─── YETKİ KONTROL ───────────────────────────────────────────────────────────
def is_super(uid):
    return str(uid) == str(ADMIN_ID) or adminler.get(str(uid), {}).get("seviye") == "super"

def is_yonetici(uid):
    return is_super(uid) or adminler.get(str(uid), {}).get("seviye") == "yonetici"

def is_saha(uid):
    return is_yonetici(uid) or adminler.get(str(uid), {}).get("seviye") == "saha"

def seviye_adi(uid):
    if is_super(uid): return "🔴 Super Admin"
    s = adminler.get(str(uid), {}).get("seviye", "")
    if s == "yonetici": return "🟡 Yonetici"
    if s == "saha": return "🟢 Saha"
    return "❌ Yetkisiz"

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
        await edit("İptal edildi.", None)
        return
    if q.data == "giris_geri":
        await edit(giris_metni(q.from_user), giris_kb())
        return
    il = q.data.split(":", 1)[1]
    context.user_data["il"] = il
    aktif_ilceler = [ilce for ilce in konumlar.get(il, {}) if ilce_konum_sayisi(il, ilce) > 0]
    if not aktif_ilceler:
        await edit(f"{il} ilinde aktif bölge yok.", None)
        return
    kb = [[InlineKeyboardButton(f"📌 {ilce}", callback_data=f"ilce:{ilce}")] for ilce in aktif_ilceler]
    kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="giris_geri")])
    kb.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])
    await edit(f"Il: {il}\n\nBölge seçin:", InlineKeyboardMarkup(kb))

async def ilce_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "iptal":
        await q.edit_message_text("İptal edildi.")
    if q.data == "geri_il":
        aktif = [il for il, ilceler in konumlar.items() if any(ilce_konum_sayisi(il, ilce) > 0 for ilce in ilceler)]
        kb = [[InlineKeyboardButton(f"📍 {il}", callback_data=f"il:{il}")] for il in aktif]
        kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="giris_geri")])
        kb.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])
        await q.edit_message_text("Il seçin:", reply_markup=InlineKeyboardMarkup(kb))
    ilce = q.data.split(":", 1)[1]
    il   = context.user_data["il"]
    context.user_data["ilce"] = ilce
    urunler = ilce_urunler(il, ilce)
    if not urunler:
        await q.edit_message_text(f"{ilce} bölgesinde ürün bulunamadı.")
    kb = [[InlineKeyboardButton(ad, callback_data=f"ürün:{ad}")] for ad in urunler.keys()]
    kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_il")])
    kb.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])
    await q.edit_message_text(f"Il: {il}  |  Bölge: {ilce}\n\nÜrün seçin:", reply_markup=InlineKeyboardMarkup(kb))

async def urun_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "iptal":
        await q.edit_message_text("İptal edildi.")
    if q.data == "geri_il":
        il = context.user_data["il"]
        aktif_ilceler = [ilce for ilce in konumlar.get(il, {}) if ilce_konum_sayisi(il, ilce) > 0]
        kb = [[InlineKeyboardButton(f"📌 {ilce}", callback_data=f"ilce:{ilce}")] for ilce in aktif_ilceler]
        kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_il")])
        kb.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])
        await q.edit_message_text("Bölge seçin:", reply_markup=InlineKeyboardMarkup(kb))
    urun_ad = q.data.split(":", 1)[1]
    il      = context.user_data["il"]
    ilce    = context.user_data["ilce"]
    context.user_data["urun_ad"] = urun_ad
    urunler = ilce_urunler(il, ilce)
    gramlar = urunler.get(urun_ad, {})
    kb = [[InlineKeyboardButton(f"{g}  —  {miktar_fiyat_str(f)}", callback_data=f"gram:{g}")] for g, f in gramlar.items()]
    kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_il")])
    kb.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])
    await q.edit_message_text(f"Il: {il}  |  Bölge: {ilce}\nÜrün: {urun_ad}\n\nMiktar seçin:", reply_markup=InlineKeyboardMarkup(kb))

async def gram_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "iptal":
        await q.edit_message_text("İptal edildi.")
    if q.data == "geri_ilce":
        il   = context.user_data["il"]
        ilce = context.user_data["ilce"]
        urunler = ilce_urunler(il, ilce)
        kb = [[InlineKeyboardButton(ad, callback_data=f"ürün:{ad}")] for ad in urunler.keys()]
        kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_il")])
        kb.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])
        await q.edit_message_text("Ürün seçin:", reply_markup=InlineKeyboardMarkup(kb))
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
        ind_txt = f"🎁 {kalan} sipariş sonra %{INDIRIM_ORANI} indirim!\n"
    else:
        ind_txt = ""
    ozet = (
        f"Sipariş Ozeti\n─────────────────\n"
        f"Sipariş No : {no}\n"
        f"Il         : {il}\n"
        f"Bölge      : {ilce}\n"
        f"Ürün       : {urun_ad}\n"
        f"Miktar     : {gram}\n"
        f"─────────────────\n"
        f"IBAN Fiyatı : {fiyat_str(tl_f)} TL\n"
        f"TRC20 Fiyatı : {fiyat_str(usd_f)} USD\n"
        f"─────────────────\n"
        f"{ind_txt}\n"
        f"Ödeme yontemini seçin:"
    )
    kb = [
        [InlineKeyboardButton("🏦 IBAN / Havale", callback_data="odeme_iban")],
        [InlineKeyboardButton("💎 TRC20 (USDT)",  callback_data="odeme_trc20")],
        [InlineKeyboardButton("⬅️ Geri",           callback_data="geri_odeme_sec")],
        [InlineKeyboardButton("❌ İptal",           callback_data="iptal")],
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
        await edit("İptal edildi.")
        return

    if q.data in ("geri_ilce", "geri_odeme_sec"):
        il      = context.user_data.get("il", "")
        ilce    = context.user_data.get("ilce", "")
        urun_ad = context.user_data.get("urun_ad", "")
        urunler = ilce_urunler(il, ilce)
        gramlar = urunler.get(urun_ad, {})
        kb = [[InlineKeyboardButton(f"{g}  —  {miktar_fiyat_str(f)}", callback_data=f"gram:{g}")] for g, f in gramlar.items()]
        kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_ilce")])
        kb.append([InlineKeyboardButton("❌ İptal", callback_data="iptal")])
        try:
            await q.message.delete()
        except:
            pass
        await q.message.chat.send_message("Miktar seçin:", reply_markup=InlineKeyboardMarkup(kb))
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
            f"Sipariş Ozeti\n─────────────────\n"
            f"Sipariş No : {no}\n"
            f"Ürün       : {urun_ad} {gram}\n"
            f"Fiyat      : {fiyat_goster}\n"
            f"─────────────────\n\n"
            f"{bilgi}\n\n"
            f"Ödemeyi yaptiktan sonra dekont fotoğrafini gönderin."
        )
        kb = [
            [InlineKeyboardButton("✅ Siparişi Onayla", callback_data="onayla")],
            [InlineKeyboardButton("⬅️ Geri",            callback_data="geri_odeme")],
            [InlineKeyboardButton("❌ İptal",            callback_data="iptal")],
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
        await q.edit_message_text("İptal edildi.")
        return
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
        ind_txt = f"🎉 %{INDIRIM_ORANI} INDIRIM UYGULANDL!\n" if aktif else (f"🎁 {kalan} sipariş sonra indirim!\n" if kalan > 0 else "")
        ozet = (
            f"Sipariş Ozeti\n─────────────────\n"
            f"Sipariş No : {no}\n"
            f"Il         : {il}\n"
            f"Bölge      : {ilce}\n"
            f"Ürün       : {urun_ad}\n"
            f"Miktar     : {gram}\n"
            f"─────────────────\n"
            f"IBAN Fiyatı : {fiyat_str(tl_f)} TL\n"
            f"TRC20 Fiyatı : {fiyat_str(usd_f)} USD\n"
            f"─────────────────\n{ind_txt}\nÖdeme yontemini seçin:"
        )
        kb = [
            [InlineKeyboardButton("🏦 IBAN / Havale", callback_data="odeme_iban")],
            [InlineKeyboardButton("💎 TRC20 (USDT)",  callback_data="odeme_trc20")],
            [InlineKeyboardButton("⬅️ Geri",           callback_data="geri_ilce")],
            [InlineKeyboardButton("❌ İptal",           callback_data="iptal")],
        ]
        await q.edit_message_text(ozet, reply_markup=InlineKeyboardMarkup(kb))
        return
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
            "ödeme":      context.user_data.get("odeme_yontemi", ""),
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
        siparisler[no]["rezerve_zaman"] = time.time()
        kaydet(S_DOSYA, siparisler)
        yontem = "Havale/EFT" if context.user_data.get("odeme_yontemi") == "odeme_iban" else "TRC20 (USDT)"
        await edit(
            f"Siparişıniz alındı!\n\nSipariş No: {no}\nÖdeme: {yontem}\n\n"
            f"Dekontu gönderin. (10 dakika icinde gönderin!)"
        )

# ─── DEKONT ──────────────────────────────────────────────────────────────────
async def foto_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    # Admin işlem modu kontrolü - sadece adm dict'te aktif işlem varsa admin olarak işle
    if uid in adm:
        if adm[uid].get("adim") == "giriş_foto":
            ayarlar["giriş_foto_id"] = update.message.photo[-1].file_id
            kaydet(A_DOSYA, ayarlar)
            del adm[uid]
            await update.message.reply_text("Giriş görseli ayarlandi!\n\n/start ile test edebilirsin.")
            return
        if adm[uid].get("adim") == "u_foto":
            hid = adm[uid].get("hid")
            if hid and isinstance(havuz.get(hid), dict):
                havuz[hid]["foto_id"] = update.message.photo[-1].file_id
                kaydet(H_DOSYA, havuz)
                del adm[uid]
                await update.message.reply_text("✅ Ürün görseli kaydedildi!")
            else:
                await update.message.reply_text("Hata: ürün bulunamadı.")
            return
        if adm[uid].get("adim") == "foto":
            adm[uid]["foto_id"] = update.message.photo[-1].file_id
            adm[uid]["adim"]    = "konum"
            await update.message.reply_text("Fotoğraf kaydedildi!\n\nŞimdi konumu gönder:")
            return
    # Admin ama aktif işlem yoksa - foto ID ver (sadece süper admin)
    if is_super(uid) and uid not in adm:
        await update.message.reply_text(f"Fotoğraf ID:\n{update.message.photo[-1].file_id}")
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
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛒 Sipariş Oluştur", url=f"https://t.me/{(await context.bot.get_me()).username}")]])
        await update.message.reply_text(
            "Aktif siparişıniz bulunmuyor.\nSipariş oluşturmak icin /start yazin.",
        )
        return

    s = siparisler[no]

    # İki fotoğraf gelirse sadece müşteriye bilgi ver, admine tekrar gönderme
    if s.get("dekont_gonderildi"):
        await update.message.reply_text(
            f"Dekontunuz zaten alındı!\nSipariş No: {no}\n\nAdmin onayı bekleniyor."
        )
        return

    siparisler[no]["dekont_gonderildi"] = True
    kaydet(S_DOSYA, siparisler)

    kb = [[InlineKeyboardButton(f"✅ Onayla — {no}", callback_data=f"onay:{no}"),
           InlineKeyboardButton(f"❌ Reddet — {no}", callback_data=f"ret:{no}")]]
    caption = (
        f"Yeni Dekont!\nNo: {no}\n"
        f"Il/İlçe: {s.get('il','?')}/{s.get('ilce','?')}\n"
        f"Ürün: {s.get('urun','?')}\n"
        f"Fiyat: {fiyat_str(s.get('fiyat',0))}\n\nOnaylamak için:"
    )
    # Süper admin hariç tüm adminlere gönder
    for aid, a in adminler.items():
        if a.get("seviye") == "super":
            continue
        try:
            await context.bot.send_photo(
                chat_id=int(aid),
                photo=update.message.photo[-1].file_id,
                caption=caption,
                reply_markup=InlineKeyboardMarkup(kb)
            )
        except Exception as e:
            logger.error(f"Admin {aid} e dekont gönderilemedi: {e}")
    await update.message.reply_text(f"Dekontunuz alındı! Sipariş No: {no}")

# ─── KONUM ───────────────────────────────────────────────────────────────────
async def konum_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_saha(uid):
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
    await update.message.reply_text("Konum kaydedildi!\n\nÜrünu seç:", reply_markup=InlineKeyboardMarkup(kb))

# ─── ADMİN CALLBACK ──────────────────────────────────────────────────────────
async def adm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    # onay ve ret sadece yönetici yapabilir (süper admin değil)
    if q.data.startswith("onay:") or q.data.startswith("ret:"):
        if not is_yonetici(uid) or is_super(uid):
            await q.answer("Bu işlemi sadece Yönetici yapabilir!", show_alert=True)
            return
    # ks: ve ksg: (konum için ürün/gramaj seçimi) saha da yapabilir
    elif q.data.startswith("ks:") or q.data.startswith("ksg:") or q.data.startswith("yeni_k:") or q.data == "tamam":
        if not is_saha(uid):
            await q.answer("Yetkisiz!", show_alert=True)
            return
    elif not is_yonetici(uid):
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
        adm[q.from_user.id] = {"adim": "gramaj_sec", "il": il, "ilce": ilce, "kidx": kidx, "urun_ad": ad, "hid": hid}
        kb   = [[InlineKeyboardButton(f"{g}  —  {miktar_fiyat_str(f)}", callback_data=f"ksg:{hid}:{g}:{il}:{ilce}:{kidx}")]
                for g, f in mik.items()]
        await q.edit_message_text(f"Ürün: {ad}\n\nGramaji seç:", reply_markup=InlineKeyboardMarkup(kb))

    elif d.startswith("ksg:"):
        p    = d.split(":")
        hid  = p[1]; gram = p[2]; il = p[3]; ilce = p[4]; kidx = int(p[5])
        hu   = havuz.get(hid, {})
        ad   = hu.get("ad", "?")
        fobj = hu.get("miktarlar", {}).get(gram, {})
        konumlar[il][ilce][kidx]["urun"] = {"ad": ad, "gram": gram, "fiyat": fobj}
        kaydet(K_DOSYA, konumlar)
        if ADMIN_ID in adm: del adm[q.from_user.id]
        kalan = ilce_konum_sayisi(il, ilce)
        kb = [
            [InlineKeyboardButton("⚡ Ayni İlçeye Hızlı Ekle", callback_data=f"yeni_k:{il}:{ilce}")],
            [InlineKeyboardButton("📍 Baska İlçe/Il Ekle",     callback_data="konum_ekle_menu")],
            [InlineKeyboardButton("✅ Tamamlandı",              callback_data="tamam")],
        ]
        await q.edit_message_text(
            f"✅ Kaydedildi! ({kalan}. konum)\n{il}/{ilce} — {ad} {gram} — {miktar_fiyat_str(fobj)}\n\nDevam etmek ister misiniz?",
            reply_markup=InlineKeyboardMarkup(kb)
        )

    elif d.startswith("yeni_k:"):
        p = d.split(":"); il = p[1]; ilce = p[2]
        adm[q.from_user.id] = {"adim": "foto", "il": il, "ilce": ilce}
        await q.edit_message_text(
            f"⚡ Hızlı Ekleme Modu\n{il} / {ilce}\n\nFotoğrafi gönder:"
        )

    elif d == "tamam":
        await q.edit_message_text("Tamamlandı! /konum_ekle ile yeni konum ekleyebilirsin.")

    elif d == "konum_ekle_menu":
        iller = list(konumlar.keys())
        kb = [[InlineKeyboardButton(f"📍 {il}", callback_data=f"ke_il:{il}")] for il in iller]
        kb.append([InlineKeyboardButton("➕ Yeni İl", callback_data="ke_yeni_il")])
        await q.edit_message_text("Il seç:", reply_markup=InlineKeyboardMarkup(kb))

    elif d.startswith("ret:"):
        no = d.split(":")[1]
        s  = siparisler.get(no)
        if not s:
            await q.answer("Sipariş bulunamadı!", show_alert=True)
            return
        if s["durum"] in ("tamamlandı", "reddedildi", "işleniyor"):
            await q.answer("Bu sipariş zaten isleme alındı!", show_alert=True)
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
            [InlineKeyboardButton("🛒 Alışverişe Başla", callback_data="giris_alisveris")],
            [InlineKeyboardButton("🆘 Destek", url=ayarlar.get("destek_link", "https://t.me/destekkullanici"))],
        ])
        await context.bot.send_message(
            chat_id=mid,
            text=(
                f"Siparişıniz reddedildi.\n\n"
                f"Sipariş No: {no}\n\n"
                f"Detayli bilgi icin destek hattimizla iletisime gecebilirsiniz."
            ),
            reply_markup=red_kb
        )
        await q.edit_message_caption(f"❌ Reddedildi! {no}")
        # Diğer non-super adminlere bildir
        for aid, a in adminler.items():
            if int(aid) != q.from_user.id and a.get("seviye") != "super":
                try:
                    await context.bot.send_message(
                        chat_id=int(aid),
                        text=f"❌ {no} siparişi reddedildi."
                    )
                except:
                    pass

    elif d.startswith("onay:"):
        no = d.split(":")[1]
        s  = siparisler.get(no)
        if not s:
            await q.edit_message_caption("Sipariş bulunamadı.")
            return
        if s["durum"] in ("işleniyor", "tamamlandı", "reddedildi"):
            durum_txt = {"işleniyor": "işleniyor", "tamamlandı": "onaylandı", "reddedildi": "reddedildi"}
            await q.answer(f"Bu sipariş zaten {durum_txt.get(s['durum'], s['durum'])}!", show_alert=True)
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
            await q.edit_message_caption(f"{il}/{ilce} icin müsait konum yok!")
            return
        siparisler[no]["durum"] = "işleniyor"
        kaydet(S_DOSYA, siparisler)
        mid = s["user_id"]
        await context.bot.send_photo(chat_id=mid, photo=k["foto_id"],
            caption=f"Siparişıniz hazırlandı!\nNo: {no}\nAsagidaki konumdan teslim alın.")
        await context.bot.send_location(chat_id=mid, latitude=k["lat"], longitude=k["lon"])
        await context.bot.send_message(chat_id=mid, text=f"Teslimata hazır!\nNo: {no}\n\nİyi günler!")
        for km in konumlar.get(il, {}).get(ilce, []):
            if km["id"] == k["id"]:
                km["silindi"]  = True
                km["rezerve"]  = False
                km.pop("rezerve_no", None)
                break
        kaydet(K_DOSYA, konumlar)
        siparisler[no]["durum"] = "tamamlandı"
        kaydet(S_DOSYA, siparisler)
        musteri_guncelle(mid, s.get("musteri_ad", ""))
        yeni_t    = musteri_tamamlanan(mid)
        yeni_k    = musteri_kalan(mid)
        if yeni_k == 0:
            await context.bot.send_message(chat_id=mid,
                text=f"Tebrikler! {yeni_t}. siparişini tamamladin!\nBir sonraki siparişte %{INDIRIM_ORANI} indirim kazandın!")
        elif yeni_k <= 2:
            await context.bot.send_message(chat_id=mid,
                text=f"%{INDIRIM_ORANI} indirim için {yeni_k} siparişin kaldi!")
        kalan = ilce_konum_sayisi(il, ilce)
        uyari = f"\n\n{il}/{ilce}: {kalan} konum kaldı!" if kalan <= 3 else ""
        await q.edit_message_caption(f"✅ Tamamlandı! {no} — {yeni_t}. sipariş{uyari}")
        # Diğer non-super adminlere bildir
        for aid, a in adminler.items():
            if int(aid) != q.from_user.id and a.get("seviye") != "super":
                try:
                    await context.bot.send_message(
                        chat_id=int(aid),
                        text=f"✅ {no} siparişi onaylandı."
                    )
                except:
                    pass

# ─── ADMİN: /konum_ekle ──────────────────────────────────────────────────────
async def konum_ekle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_saha(update.effective_user.id): return
    uid = update.effective_user.id
    if uid in adm: del adm[uid]
    iller = list(konumlar.keys())
    kb = [[InlineKeyboardButton(f"📍 {il}", callback_data=f"ke_il:{il}")] for il in iller]
    kb.append([InlineKeyboardButton("➕ Yeni İl", callback_data="ke_yeni_il")])
    await update.message.reply_text("Il seç:", reply_markup=InlineKeyboardMarkup(kb))

async def ke_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_saha(q.from_user.id):
        await q.answer("Yetkisiz!", show_alert=True); return
    await q.answer()
    d = q.data
    if d == "ke_yeni_il":
        adm[q.from_user.id] = {"adim": "yeni_il"}
        await q.edit_message_text("Yeni il adını yazın:")
    elif d.startswith("ke_il:"):
        il = d.split(":", 1)[1]
        ilceler = list(konumlar.get(il, {}).keys())
        kb = [[InlineKeyboardButton(f"📌 {ilce}", callback_data=f"ke_ilce:{il}:{ilce}")] for ilce in ilceler]
        kb.append([InlineKeyboardButton("➕ Yeni İlçe", callback_data=f"ke_yeni_ilce:{il}")])
        await q.edit_message_text(f"Il: {il}\n\nİlçe seç:", reply_markup=InlineKeyboardMarkup(kb))
    elif d.startswith("ke_yeni_ilce:"):
        il = d.split(":", 1)[1]
        adm[q.from_user.id] = {"adim": "yeni_ilce", "il": il}
        await q.edit_message_text(f"{il} icin ilce adini yaz:")
    elif d.startswith("ke_ilce:"):
        p = d.split(":"); il = p[1]; ilce = p[2]
        adm[q.from_user.id] = {"adim": "foto", "il": il, "ilce": ilce}
        await q.edit_message_text(f"{il}/{ilce}\n\nFotoğrafi gönder:")
    elif d.startswith("yeni_k:"):
        p = d.split(":"); il = p[1]; ilce = p[2]
        adm[q.from_user.id] = {"adim": "foto", "il": il, "ilce": ilce}
        await q.edit_message_text(
            f"⚡ Hızlı Ekleme Modu\n{il} / {ilce}\n\nFotoğrafi gönder:"
        )

# ─── ADMİN: /ürünler ─────────────────────────────────────────────────────────
async def goster_havuz(hedef):
    msg = "Ürün Havuzu\n─────────────────\n"
    for hid, u in havuz.items():
        ad  = u["ad"] if isinstance(u, dict) else u
        tip = u.get("tip", "gram") if isinstance(u, dict) else "gram"
        mik = u.get("miktarlar", {}) if isinstance(u, dict) else {}
        mik_txt = "  ".join([f"{m}: {miktar_fiyat_str(f)}" for m, f in mik.items()]) if mik else "Miktar yok"
        msg += f"\n{ad} [{tip_label(tip)}]\n  {mik_txt}\n"
    msg += "\nDuzenlemek icin seçin:"
    kb = [[InlineKeyboardButton(u["ad"] if isinstance(u, dict) else u, callback_data=f"u_detay:{hid}")]
          for hid, u in havuz.items()]
    kb.append([InlineKeyboardButton("➕ Yeni Ürün Ekle", callback_data="u_ekle")])
    markup = InlineKeyboardMarkup(kb)
    if hasattr(hedef, "reply_text"):
        await hedef.reply_text(msg, reply_markup=markup)
    else:
        await hedef.edit_message_text(msg, reply_markup=markup)

async def urunler_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_yonetici(update.effective_user.id): return
    uid = update.effective_user.id
    if uid in adm: del adm[uid]  # Önceki yarım işlemi temizle
    await goster_havuz(update.message)

async def urun_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_yonetici(q.from_user.id):
        await q.answer("Yetkisiz!", show_alert=True); return
    await q.answer()
    d = q.data

    if d == "u_ekle":
        adm[q.from_user.id] = {"adim": "u_ad"}
        await q.edit_message_text("Yeni ürün adini yaz:")

    elif d.startswith("u_tip_"):
        tip = d.replace("u_tip_", "")
        adm[q.from_user.id]["tip"]  = tip
        adm[q.from_user.id]["adim"] = "u_miktar"
        ad = adm[q.from_user.id].get("urun_ad", "?")
        ipucu = {"gram": "örn: 1g, 3.5g", "tekli": "örn: 1 Adet", "kutu": "örn: 1 Kutu"}.get(tip, "")
        await q.edit_message_text(f"Ürün: {ad} [{tip_label(tip)}]\n\nMiktar yaz ({ipucu}):")

    elif d.startswith("u_detay:"):
        hid = d.split(":")[1]
        u   = havuz.get(hid, {})
        ad  = u["ad"] if isinstance(u, dict) else u
        tip = u.get("tip", "gram") if isinstance(u, dict) else "gram"
        mik = u.get("miktarlar", {}) if isinstance(u, dict) else {}
        mik_txt = "\n".join([f"  {m}: {miktar_fiyat_str(f)}" for m, f in mik.items()]) or "  Miktar yok"
        foto_durum = "✅ Foto var" if u.get("foto_id") else "❌ Foto yok"
        kb = [
            [InlineKeyboardButton(f"🖼 Fotoğraf Ekle/Değiştir ({foto_durum})", callback_data=f"u_foto:{hid}")],
            [InlineKeyboardButton("➕ Miktar/Fiyat Ekle", callback_data=f"u_mik_ekle:{hid}")],
            [InlineKeyboardButton("➖ Miktar Sil",        callback_data=f"u_mik_sil:{hid}")],
            [InlineKeyboardButton("🗑 Ürünu Sil",         callback_data=f"u_sil:{hid}")],
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
        adm[q.from_user.id] = {"adim": "u_miktar", "hid": hid, "yeni": False}
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
        adm[q.from_user.id] = {"adim": "u_foto", "hid": hid}
        await q.edit_message_text("Ürün fotoğrafini gönder:")

    elif d.startswith("u_sil:"):
        hid = d.split(":")[1]
        u   = havuz.pop(hid, {})
        ad  = u["ad"] if isinstance(u, dict) else u
        kaydet(H_DOSYA, havuz)
        await q.edit_message_text(f"'{ad}' silindi!")

    elif d == "u_gramaj_devam":
        islem = adm.get(ADMIN_ID, {})
        tip   = islem.get("tip", "gram")
        adm[q.from_user.id]["adim"] = "u_miktar"
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
        adm[q.from_user.id] = {"adim": "u_foto", "hid": hid}
        await q.edit_message_text(f"'{ad}' kaydedildi!\n\nŞimdi ürün fotoğrafini gönder:")

    elif d == "u_gramaj_kaydet":
        islem    = adm.get(ADMIN_ID, {})
        ad       = islem.get("urun_ad", "")
        hid      = islem.get("hid", f"h{int(time.time())}")
        tip      = islem.get("tip", "gram")
        miktarlar = islem.get("miktarlar", {})
        havuz[hid] = {"ad": ad, "tip": tip, "miktarlar": miktarlar}
        kaydet(H_DOSYA, havuz)
        if ADMIN_ID in adm: del adm[q.from_user.id]
        mik_txt = "  ".join([f"{m}: {miktar_fiyat_str(f)}" for m, f in miktarlar.items()])
        await q.edit_message_text(f"'{ad}' [{tip_label(tip)}] eklendi!\n\n{mik_txt}")

# ─── ADMİN: /ayarlar ─────────────────────────────────────────────────────────
async def ayarlar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_yonetici(update.effective_user.id): return
    uid = update.effective_user.id
    if uid in adm: del adm[uid]
    await goster_ayarlar(update.message)

async def goster_ayarlar(hedef):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🖼 Giriş Görseli",      callback_data="ay_foto")],
        [InlineKeyboardButton("📢 Kanal Linki",         callback_data="ay_kanal")],
        [InlineKeyboardButton("🆘 Destek Linki",        callback_data="ay_destek")],
        [InlineKeyboardButton("📋 Market Kuralları",    callback_data="ay_kurallar")],
    ])
    txt = (
        f"Bot Ayarları\n─────────────────\n\n"
        f"Giriş Görseli : {'Ayarli ✅' if ayarlar.get('giris_foto_id') else 'Ayarlanmamis ❌'}\n"
        f"Kanal Link    : {ayarlar.get('kanal_link', '-')}\n"
        f"Destek Link   : {ayarlar.get('destek_link', '-')}\n"
        f"Market Kurali : {'Ayarli ✅' if ayarlar.get('market_kurali') else 'Boş ❌'}\n"
    )
    if hasattr(hedef, "reply_text"):
        await hedef.reply_text(txt, reply_markup=kb)
    else:
        await hedef.edit_message_text(txt, reply_markup=kb)

async def ayarlar_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_yonetici(q.from_user.id):
        await q.answer("Yetkisiz!", show_alert=True); return
    await q.answer()
    d = q.data

    if d == "ay_foto":
        adm[q.from_user.id] = {"adim": "giriş_foto"}
        await q.edit_message_text("Giriş icin görsel gönder:")

    elif d == "ay_kanal":
        adm[q.from_user.id] = {"adim": "ay_kanal"}
        await q.edit_message_text(
            f"Mevcut kanal linki:\n{ayarlar.get('kanal_link', '-')}\n\nYeni linki yaz:"
        )

    elif d == "ay_destek":
        adm[q.from_user.id] = {"adim": "ay_destek"}
        await q.edit_message_text(
            f"Mevcut destek linki:\n{ayarlar.get('destek_link', '-')}\n\nYeni linki yaz:"
        )

    elif d == "ay_kurallar":
        adm[q.from_user.id] = {"adim": "ay_kurallar"}
        await q.edit_message_text("Yeni market kurallarıni yaz:")

    elif d == "ay_geri":
        await goster_ayarlar(q)

# ─── ADMİN: /ödeme ───────────────────────────────────────────────────────────
async def odeme_yonetim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_yonetici(update.effective_user.id): return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏦 IBAN Düzenle",  callback_data="ody_iban")],
        [InlineKeyboardButton("💎 TRC20 Düzenle", callback_data="ody_trc20")],
    ])
    await update.message.reply_text(
        f"Ödeme Bilgileri\n─────────────────\n\nIBAN:\n{odeme_bilgileri.get('iban','')}\n\n"
        f"─────────────\n\nTRC20:\n{odeme_bilgileri.get('trc20','')}\n\nDuzenlemek icin seç:",
        reply_markup=kb
    )

async def odeme_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_yonetici(q.from_user.id):
        await q.answer("Yetkisiz!", show_alert=True); return
    await q.answer()
    if q.data == "ody_iban":
        adm[q.from_user.id] = {"adim": "iban_guncelle"}
        await q.edit_message_text("Yeni IBAN bilgilerini yazın:")
    elif q.data == "ody_trc20":
        adm[q.from_user.id] = {"adim": "trc20_guncelle"}
        await q.edit_message_text("Yeni TRC20 adresini yazın:")

# ─── METİN ───────────────────────────────────────────────────────────────────
async def metin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    txt  = update.message.text.strip()
    user = update.effective_user

    # Referans kodu bekleniyor
    if context.user_data.get("bekleyen_kod") and not is_saha(uid):
        kod = txt.upper().strip()
        if kod in kodlar and not kodlar[kod].get("kullanildi"):
            # Kod geçerli - kayıt et
            musteri_kaydet_kod(uid, user.first_name or "", kod)
            context.user_data.pop("bekleyen_kod", None)
            foto = ayarlar.get("giris_foto_id", "")
            await update.message.reply_text(
                f"Hoşgeldiniz {user.first_name}! Kaydiniz oluşturuldu."
            )
            if foto:
                await update.message.reply_photo(photo=foto, caption=giris_metni(user), reply_markup=giris_kb())
            else:
                await update.message.reply_text(giris_metni(user), reply_markup=giris_kb())
        else:
            await update.message.reply_text(
                "Geçersiz veya kullanılmış kod!\n\n"
                "Lütfen gecerli bir referans kodu girin."
            )
        return

    if is_saha(uid) and uid in adm:
        a = adm[uid]

        if a["adim"] == "yeni_il":
            if txt not in konumlar: konumlar[txt] = {}; kaydet(K_DOSYA, konumlar)
            # adm'ı silme, ilce seçimine yönlendir
            adm[uid] = {"adim": "il_secildi", "il": txt}
            ilceler = list(konumlar.get(txt, {}).keys())
            kb = [[InlineKeyboardButton(f"📌 {ilce}", callback_data=f"ke_ilce:{txt}:{ilce}")] for ilce in ilceler]
            kb.append([InlineKeyboardButton("➕ Yeni Ilce", callback_data=f"ke_yeni_ilce:{txt}")])
            await update.message.reply_text(f"'{txt}' eklendi!\n\nİlçe seç:", reply_markup=InlineKeyboardMarkup(kb))
            return

        elif a["adim"] == "yeni_ilce":
            il = a["il"]
            if il not in konumlar: konumlar[il] = {}
            if txt not in konumlar[il]: konumlar[il][txt] = []; kaydet(K_DOSYA, konumlar)
            adm[uid] = {"adim": "foto", "il": il, "ilce": txt}
            await update.message.reply_text(f"'{txt}' eklendi!\n\nFotoğrafi gönder:")
            return

        elif a["adim"] == "u_ad":
            adm[uid] = {"adim": "u_tip_bekleniyor", "urun_ad": txt, "hid": f"h{int(time.time())}", "miktarlar": {}, "yeni": True}
            kb = [
                [InlineKeyboardButton("⚖️ Gram",         callback_data="u_tip_gram")],
                [InlineKeyboardButton("1️⃣ Tekli (Adet)", callback_data="u_tip_tekli")],
                [InlineKeyboardButton("📦 Kutu",          callback_data="u_tip_kutu")],
            ]
            await update.message.reply_text(f"Ürün: {txt}\n\nSatis tipini seç:", reply_markup=InlineKeyboardMarkup(kb))
            return

        elif a["adim"] == "u_miktar":
            a["gecici_miktar"] = txt
            a["adim"]          = "u_fiyat_tl"
            await update.message.reply_text(f"'{txt}' icin TL fiyatını yazın:")
            return

        elif a["adim"] == "u_fiyat_tl":
            try:
                tl = float(txt.replace(",", "."))
                a["gecici_tl"] = tl
                a["adim"]      = "u_fiyat_usd"
                await update.message.reply_text(f"'{a['gecici_miktar']}' icin Dolar (USD) fiyatini yaz:")
            except:
                await update.message.reply_text("Geçersiz! Sayi gir (örn: 450)")
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
                        [InlineKeyboardButton("✅ Kaydet (Görselsiz)", callback_data="u_gramaj_kaydet")],
                        [InlineKeyboardButton("🖼 Görsel Ekle ve Kaydet", callback_data="u_gorsel_ekle")],
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
                await update.message.reply_text("Geçersiz! Sayi gir (örn: 14)")
            return

        elif a["adim"] == "ay_kanal":
            ayarlar["kanal_link"] = txt
            kaydet(A_DOSYA, ayarlar)
            del adm[uid]
            await update.message.reply_text(f"Kanal linki güncellendi!\n{txt}")
            return

        elif a["adim"] == "ay_destek":
            ayarlar["destek_link"] = txt
            kaydet(A_DOSYA, ayarlar)
            del adm[uid]
            await update.message.reply_text(f"Destek linki güncellendi!\n{txt}")
            return

        elif a["adim"] == "ay_kurallar":
            ayarlar["market_kurali"] = txt
            kaydet(A_DOSYA, ayarlar)
            del adm[uid]
            await update.message.reply_text("Market kurallari güncellendi!")
            return

        elif a["adim"] == "adm_id_bekle":
            try:
                yeni_uid = int(txt.strip())
                adm[uid] = {"adim": "adm_ad_bekle", "yeni_uid": yeni_uid}
                await update.message.reply_text(f"ID: {yeni_uid}\n\nBu adminin adini yaz:")
            except:
                await update.message.reply_text("Geçersiz ID! Sadece rakam gir.")
            return

        elif a["adim"] == "adm_ad_bekle":
            yeni_uid = a.get("yeni_uid")
            # Adı adm dict'te sakla, callback'e koyma
            adm[uid] = {"adim": "adm_sev_bekle", "yeni_uid": yeni_uid, "yeni_ad": txt}
            sev_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔴 Super Admin", callback_data="adm_sev_sec_super")],
                [InlineKeyboardButton("🟡 Yonetici",    callback_data="adm_sev_sec_yonetici")],
                [InlineKeyboardButton("🟢 Saha",        callback_data="adm_sev_sec_saha")],
            ])
            await update.message.reply_text(f"Ad: {txt}\nSeviyeyi seç:", reply_markup=sev_kb)
            return

        elif a["adim"] == "iban_guncelle":
            odeme_bilgileri["iban"] = "Ödeme Yontemi: IBAN / Havale\n─────────────────\n" + txt
            kaydet(O_DOSYA, odeme_bilgileri)
            del adm[uid]
            await update.message.reply_text("IBAN güncellendi!")
            return

        elif a["adim"] == "trc20_guncelle":
            odeme_bilgileri["trc20"] = "Ödeme Yontemi: TRC20 (USDT)\n─────────────────\nAdres: " + txt + "\n\nGöndermeden önce adresi kontrol edin!"
            kaydet(O_DOSYA, odeme_bilgileri)
            del adm[uid]
            await update.message.reply_text("TRC20 güncellendi!")
            return

    await update.message.reply_text("Sipariş vermek icin /start yazin.")

# ─── KOMUTLAR ────────────────────────────────────────────────────────────────
async def konumlar_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_yonetici(update.effective_user.id): return
    if not konumlar:
        await update.message.reply_text("Hiç konum yok.")
        return
    for il, ilceler in konumlar.items():
        for ilce, liste in ilceler.items():
            kalan = ilce_konum_sayisi(il, ilce)
            e   = "🟢" if kalan > 3 else ("🟡" if kalan > 0 else "🔴")
            rezerveli = sum(1 for k in liste if k.get("rezerve") and not k.get("silindi"))
            bos       = kalan - rezerveli
            msg = f"{e} {il}/{ilce} — {boş} boş / {rezerveli} rezerveli / {len(liste)} toplam\n─────────────────"
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
    if not is_yonetici(update.effective_user.id): return
    if not siparisler:
        await update.message.reply_text("Henuz sipariş yok.")
        return
    e   = {"beklemede": "⏳", "işleniyor": "🔄", "tamamlandı": "✅"}
    msg = "Siparişler\n─────────────────\n"
    for no, s in siparisler.items():
        msg += f"\n{e.get(s['durum'],'?')} {no}\n  {s.get('il','')}/{s.get('ilce','')} | {s['urun']} | {fiyat_str(s['fiyat'])}\n"
    await update.message.reply_text(msg)

async def musteriler_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_yonetici(update.effective_user.id): return
    if not musteriler:
        await update.message.reply_text("Henuz müşteri yok.")
        return
    msg = "Müşteri Listesi\n─────────────────\n"
    for uid, m in sorted(musteriler.items(), key=lambda x: -x[1].get("tamamlanan", 0)):
        t     = m.get("tamamlanan", 0)
        ad    = m.get("ad", "?")
        kalan = musteri_kalan(int(uid))
        durum = "🎉 INDIRIM HAKKI VAR!" if t > 0 and t % INDIRIM_HER_N == 0 else f"{kalan} sipariş kaldi"
        msg  += f"\n👤 {ad}\n  Tamamlanan: {t} | {durum}\n"
    await update.message.reply_text(msg)


# ─── ADMİN YÖNETİMİ ──────────────────────────────────────────────────────────

async def ciro_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super(update.effective_user.id): return

    # Aktif siparişlerden hesapla
    aktif_tl = aktif_usd = 0.0
    for no, s in siparisler.items():
        if s.get("durum") == "tamamlandı":
            f = float(s.get("fiyat", 0))
            if s.get("odeme") == "odeme_iban":
                aktif_tl += f
            else:
                aktif_usd += f

    toplam_tl  = round(ciro.get("toplam_tl", 0) + aktif_tl, 2)
    toplam_usd = round(ciro.get("toplam_usd", 0) + aktif_usd, 2)

    msg  = f"💰 TOPLAM CİRO\n═══════════════\n\n"
    msg += f"Tum Zamanlar:\n"
    msg += f"  IBAN/TL  : {fiyat_str(toplam_tl)} TL\n"
    msg += f"  TRC20    : {fiyat_str(toplam_usd)} USD\n\n"
    msg += f"Bu Donem (Sıfırlanmamis):\n"
    msg += f"  IBAN/TL  : {fiyat_str(aktif_tl)} TL\n"
    msg += f"  TRC20    : {fiyat_str(aktif_usd)} USD\n\n"

    gunler = ciro.get("gunler", [])
    if gunler:
        msg += f"Geçmiş Gun Sonlari:\n─────────────────\n"
        for g in gunler[-10:]:  # Son 10 gün
            msg += f"  {g['tarih']}: {fiyat_str(g['tl'])} TL / {fiyat_str(g['usd'])} USD\n"

    await update.message.reply_text(msg)


async def kod_olustur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super(update.effective_user.id):
        await update.message.reply_text("Yetkisiz!")
        return
    # Kaç kod oluşturulacak
    try:
        adet = int(context.args[0]) if context.args else 1
        adet = min(adet, 50)  # Max 50
    except:
        adet = 1

    yeni_kodlar = []
    for _ in range(adet):
        kod = kod_uret(6)
        kodlar[kod] = {"kullanildi": False, "oluşturuldu": time.strftime("%d.%m.%Y %H:%M")}
        yeni_kodlar.append(kod)
    kaydet(KOD_DOSYA, kodlar)

    msg = f"{adet} adet referans kodu oluşturuldu:\n\n"
    msg += "\n".join([f"• {k}" for k in yeni_kodlar])
    await update.message.reply_text(msg)

async def kodlar_listele(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super(update.effective_user.id):
        await update.message.reply_text("Yetkisiz!")
        return
    if not kodlar:
        await update.message.reply_text("Hiç kod yok. /kod_oluştur 10 ile oluştur.")
        return
    bos    = [k for k, v in kodlar.items() if not v.get("kullanildi")]
    dolu   = [k for k, v in kodlar.items() if v.get("kullanildi")]
    msg    = f"Referans Kodları\n─────────────────\n"
    msg   += f"Boş: {len(boş)} | Kullanılmış: {len(dolu)}\n\n"
    if bos:
        msg += "Kullanılabilir Kodlar:\n"
        msg += "\n".join([f"• {k}" for k in bos[:30]])
        if len(bos) > 30:
            msg += f"\n... ve {len(boş)-30} tane daha"
    await update.message.reply_text(msg)

async def adminler_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super(update.effective_user.id):
        await update.message.reply_text("Yetkisiz!")
        return
    msg = "Admin Listesi\n─────────────────\n"
    for uid, a in adminler.items():
        msg += f"\n{seviye_adi(int(uid))}\n  {a.get('ad','?')} (ID: {uid})\n"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Admin Ekle",       callback_data="adm_ekle")],
        [InlineKeyboardButton("➖ Admin Sil",        callback_data="adm_sil_liste")],
        [InlineKeyboardButton("🔄 Seviye Değiştir",  callback_data="adm_seviye_liste")],
    ])
    await update.message.reply_text(msg, reply_markup=kb)

async def adminler_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_super(q.from_user.id):
        await q.answer("Yetkisiz!", show_alert=True)
        return
    await q.answer()
    d = q.data

    if d == "adm_ekle":
        adm[q.from_user.id] = {"adim": "adm_id_bekle"}
        await q.edit_message_text(
            "Eklenecek adminin Telegram ID'sini yaz:\n\n"
            "Kullanıcı bota /id yazarsa ID'sini ogrenir."
        )

    elif d == "adm_sil_liste":
        silinebilir = {uid: a for uid, a in adminler.items() if uid != str(ADMIN_ID)}
        if not silinebilir:
            await q.answer("Silinecek admin yok!", show_alert=True)
            return
        kb = [[InlineKeyboardButton(f"🗑 {a.get('ad','?')} ({uid})", callback_data=f"adm_sil:{uid}")]
              for uid, a in silinebilir.items()]
        kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="adm_geri")])
        await q.edit_message_text("Kimi silmek istiyorsunuz?", reply_markup=InlineKeyboardMarkup(kb))

    elif d.startswith("adm_sil:"):
        uid = d.split(":")[1]
        ad  = adminler.pop(uid, {}).get("ad", "?")
        adminler_kaydet()
        await q.edit_message_text(f"'{ad}' admin listesinden silindi!")

    elif d == "adm_seviye_liste":
        silinebilir = {uid: a for uid, a in adminler.items() if uid != str(ADMIN_ID)}
        if not silinebilir:
            await q.answer("Değiştirilecek admin yok!", show_alert=True)
            return
        kb = [[InlineKeyboardButton(f"{seviye_adi(int(uid))} — {a.get('ad','?')}", callback_data=f"adm_sev_seç:{uid}")]
              for uid, a in silinebilir.items()]
        kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="adm_geri")])
        await q.edit_message_text("Kimin seviyesini değiştirmek istiyorsun?", reply_markup=InlineKeyboardMarkup(kb))

    elif d.startswith("adm_sev_seç:"):
        uid = d.split(":")[1]
        ad  = adminler.get(uid, {}).get("ad", "?")
        kb = [
            [InlineKeyboardButton("🔴 Super Admin", callback_data=f"adm_sev_yap:{uid}:super")],
            [InlineKeyboardButton("🟡 Yonetici",    callback_data=f"adm_sev_yap:{uid}:yonetici")],
            [InlineKeyboardButton("🟢 Saha",        callback_data=f"adm_sev_yap:{uid}:saha")],
            [InlineKeyboardButton("⬅️ Geri",        callback_data="adm_seviye_liste")],
        ]
        await q.edit_message_text(f"{ad} icin yeni seviye seç:", reply_markup=InlineKeyboardMarkup(kb))

    elif d.startswith("adm_sev_yap:"):
        p   = d.split(":")
        uid = p[1]
        sev = p[2]
        if uid in adminler:
            adminler[uid]["seviye"] = sev
            adminler_kaydet()
        await q.edit_message_text(f"Seviye güncellendi: {adminler.get(uid,{}).get('ad','?')} → {sev}")

    elif d.startswith("adm_sev_yeni:"):
        p    = d.split(":")
        uid2 = p[1]
        ad2  = p[2]
        sev2 = p[3]
        adminler[uid2] = {"seviye": sev2, "ad": ad2}
        adminler_kaydet()
        await q.edit_message_text(
            f"Admin eklendi!\n\n{seviye_adi(int(uid2))}\n{ad2} (ID: {uid2})"
        )

    elif d.startswith("adm_sev_sec_"):
        sev = d.replace("adm_sev_seç_", "")
        islem = adm.get(q.from_user.id, {})
        yeni_uid = str(islem.get("yeni_uid", ""))
        yeni_ad  = islem.get("yeni_ad", "?")
        if yeni_uid:
            adminler[yeni_uid] = {"seviye": sev, "ad": yeni_ad}
            adminler_kaydet()
            if q.from_user.id in adm:
                del adm[q.from_user.id]
            sev_goster = {"super": "🔴 Super Admin", "yonetici": "🟡 Yonetici", "saha": "🟢 Saha"}.get(sev, sev)
            await q.edit_message_text(
                f"Admin eklendi!\n\n{sev_goster}\n{yeni_ad} (ID: {yeni_uid})"
            )
        else:
            await q.answer("Hata! Tekrar deneyin.", show_alert=True)

    elif d == "adm_geri":
        msg = "Admin Listesi\n─────────────────\n"
        for uid, a in adminler.items():
            msg += f"\n{seviye_adi(int(uid))}\n  {a.get('ad','?')} (ID: {uid})\n"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Admin Ekle",       callback_data="adm_ekle")],
            [InlineKeyboardButton("➖ Admin Sil",        callback_data="adm_sil_liste")],
            [InlineKeyboardButton("🔄 Seviye Değiştir",  callback_data="adm_seviye_liste")],
        ])
        await q.edit_message_text(msg, reply_markup=kb)

async def gunsonu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super(update.effective_user.id): return
    toplam = tamamlanan = bekleyen = 0
    gelir_tl = gelir_usd = 0.0
    iban_adet = trc20_adet = 0
    urun_sayac = {}
    for no, s in siparisler.items():
        toplam += 1
        if s["durum"] == "tamamlandı":
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
    rapor  = f"📊 GÜN SONU — {time.strftime('%d.%m.%Y %H:%M')}\n═══════════════\n\n"
    rapor += f"📦 Sipariş: {toplam} toplam | {tamamlanan} tamamlandı | {bekleyen} bekliyor\n\n"
    rapor += f"💰 Gelir:\n  IBAN: {fiyat_str(gelir_tl)} TL ({iban_adet})\n  TRC20: {fiyat_str(gelir_usd)} USD ({trc20_adet})\n\n"
    rapor += "🍬 Satislar:\n" + "\n".join([f"  {u}: {a}" for u, a in urun_sayac.items()]) + "\n\n" if urun_sayac else "🍬 Satis yok\n\n"
    rapor += f"📍 Konum: {kalan_k} kalan / {kullanilan_k} kullanıldı\n" + "\n".join(k_satirlar)
    kb = [[InlineKeyboardButton("🗑 Siparişleri Sıfırla", callback_data="gunsonu_sifirla")]]
    await update.message.reply_text(rapor, reply_markup=InlineKeyboardMarkup(kb))

async def gunsonu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_super(q.from_user.id):
        await q.answer("Yetkisiz!", show_alert=True); return
    await q.answer()
    if q.data == "gunsonu_sifirla":
        kb = [[InlineKeyboardButton("✅ Evet", callback_data="gunsonu_evet")],
              [InlineKeyboardButton("❌ İptal", callback_data="gunsonu_iptal")]]
        await q.edit_message_text("Emin misiniz?\n\nTum siparisler silinecek.", reply_markup=InlineKeyboardMarkup(kb))
    elif q.data == "gunsonu_evet":
        # Sıfırlamadan önce ciroya ekle
        gun_tl = 0.0
        gun_usd = 0.0
        for no, s in siparisler.items():
            if s.get("durum") == "tamamlandı":
                f = float(s.get("fiyat", 0))
                if s.get("odeme") == "odeme_iban":
                    gun_tl += f
                else:
                    gun_usd += f
        ciro["toplam_tl"]  = round(ciro.get("toplam_tl", 0) + gun_tl, 2)
        ciro["toplam_usd"] = round(ciro.get("toplam_usd", 0) + gun_usd, 2)
        ciro.setdefault("gunler", []).append({
            "tarih": time.strftime("%d.%m.%Y"),
            "tl":    gun_tl,
            "usd":   gun_usd
        })
        kaydet(C_DOSYA, ciro)
        siparisler.clear()
        kaydet(S_DOSYA, siparisler)
        await q.edit_message_text(
            f"Siparişler sıfırland! {time.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"Bu gun eklendi:\n"
            f"  IBAN: {fiyat_str(gun_tl)} TL\n"
            f"  TRC20: {fiyat_str(gun_usd)} USD\n\n"
            f"Toplam ciro:\n"
            f"  IBAN: {fiyat_str(ciro['toplam_tl'])} TL\n"
            f"  TRC20: {fiyat_str(ciro['toplam_usd'])} USD"
        )
    elif q.data == "gunsonu_iptal":
        await q.edit_message_text("İptal edildi.")

async def iptal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("İptal edildi. /start ile başlayin.")


async def id_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(f"Telegram ID'niz: {uid}")


# ─── YEDEKLeme ───────────────────────────────────────────────────────────────
async def yedek_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super(update.effective_user.id): return
    dosyalar = [K_DOSYA, H_DOSYA, M_DOSYA, A_DOSYA, ADM_DOSYA, KOD_DOSYA, O_DOSYA, C_DOSYA]
    isimler  = ["konumlar", "havuz", "musteriler", "ayarlar", "adminler", "kodlar", "ödeme", "ciro"]
    await update.message.reply_text("Yedek hazırlanıyor...")
    for dosya, isim in zip(dosyalar, isimler):
        if os.path.exists(dosya):
            with open(dosya, "r", encoding="utf-8") as f:
                icerik = f.read()
            # Dosyayı gönder
            import io
            bio = io.BytesIO(icerik.encode("utf-8"))
            bio.name = dosya
            await context.bot.send_document(
                chat_id=update.effective_user.id,
                document=bio,
                filename=dosya,
                caption=f"📁 {isim}.json"
            )
        else:
            await update.message.reply_text(f"{dosya} bulunamadı, atlanıyor.")
    await update.message.reply_text(
        "✅ Yedek tamamlandı!\n\n"
        "Bu dosyaları GitHub reposuna yukle.\n"
        "Sonraki deploy'da veriler korunacak."
    )



# ─── BOT AKTİFLİK ────────────────────────────────────────────────────────────
async def bot_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_aktif
    if not is_yonetici(update.effective_user.id):
        await update.message.reply_text("Yetkisiz!")
        return
    bot_aktif = True
    await update.message.reply_text("✅ Bot aktif! Siparişler alinabilir.")

async def bot_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_aktif
    if not is_yonetici(update.effective_user.id):
        await update.message.reply_text("Yetkisiz!")
        return
    bot_aktif = False
    await update.message.reply_text("🚫 Bot kapatıldı! Müşterilere hizmet dışı mesaji gidecek.")

async def bot_durum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_yonetici(update.effective_user.id):
        return
    durum = "✅ Aktif" if bot_aktif else "🚫 Kapalı"
    await update.message.reply_text(f"Bot Durumu: {durum}")

# ─── OTOMATİK İPTAL ──────────────────────────────────────────────────────────
REZERVE_SURE = 10 * 60  # 10 dakika saniye cinsinden



async def rezerve_kontrol_async(bot):
    """Süresi dolan rezerveleri iptal eder"""
    simdi = time.time()
    iptal_edilecek = []
    for no, s in list(siparisler.items()):
        if s.get("durum") != "beklemede":
            continue
        rezerve_zaman = s.get("rezerve_zaman")
        if not rezerve_zaman:
            continue
        if simdi - rezerve_zaman >= REZERVE_SURE:
            iptal_edilecek.append(no)
    for no in iptal_edilecek:
        s    = siparisler.get(no, {})
        il   = s.get("il", "")
        ilce = s.get("ilce", "")
        mid  = s.get("user_id")
        for km in konumlar.get(il, {}).get(ilce, []):
            if km.get("rezerve_no") == no:
                km["rezerve"] = False
                km.pop("rezerve_no", None)
                break
        kaydet(K_DOSYA, konumlar)
        siparisler[no]["durum"] = "iptal"
        kaydet(S_DOSYA, siparisler)
        if mid:
            try:
                red_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🛒 Tekrar Sipariş Ver", callback_data="giris_alisveris")],
                    [InlineKeyboardButton("🆘 Destek", url=ayarlar.get("destek_link", "https://t.me/destekkullanici"))],
                ])
                await bot.send_message(
                    chat_id=mid,
                    text=(
                        f"⏰ Siparişiniz otomatik iptal edildi.\n\n"
                        f"Sipariş No: {no}\n"
                        f"Sebep: 10 dakika içinde dekont gönderilmedi.\n\n"
                        f"Tekrar sipariş vermek için aşağıdaki butona basın."
                    ),
                    reply_markup=red_kb
                )
            except Exception as e:
                logger.error(f"İptal bildirimi gönderilemedi: {e}")
        logger.info(f"Sipariş {no} otomatik iptal edildi.")

# ─── MAIN ────────────────────────────────────────────────────────────────────
def main():
    import asyncio

    async def post_init(application):
        async def rezerve_loop():
            while True:
                await asyncio.sleep(60)
                try:
                    await rezerve_kontrol_async(application.bot)
                except Exception as e:
                    logger.error(f"Rezerve kontrol hatasi: {e}")
        asyncio.create_task(rezerve_loop())

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

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
    app.add_handler(CommandHandler("adminler",    adminler_menu))
    app.add_handler(CommandHandler("ciro",        ciro_goster))
    app.add_handler(CommandHandler("id",          id_goster))
    app.add_handler(CommandHandler("yedek",       yedek_al))
    app.add_handler(CommandHandler("on",          bot_on))
    app.add_handler(CommandHandler("off",         bot_off))
    app.add_handler(CommandHandler("durum",       bot_durum))
    app.add_handler(CommandHandler("kod_olustur", kod_olustur))
    app.add_handler(CommandHandler("kodlar",      kodlar_listele))
    app.add_handler(CallbackQueryHandler(adminler_cb, pattern=r"^adm_"))
    app.add_handler(CallbackQueryHandler(adminler_cb, pattern=r"^adm_sev_sec_"))
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

    # Her 60 saniyede bir rezerve kontrolü yap
    logger.info("Bot başladi. Rezerve kontrolu aktif (10 dk).")
    app.run_polling()

if __name__ == "__main__":
    main()
