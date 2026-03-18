"""
Telegram Sipariş Botu
=====================
Her konum: 1 foto + 1 koordinat + 1 ürün + 1 gram/fiyat
Kullanılınca silinir.
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

IL, ILCE, URUN, GRAM, ODEME = range(5)
adm = {}

S_DOSYA = "siparisler.json"
K_DOSYA = "konumlar.json"
H_DOSYA = "havuz.json"

HAVUZ_VARSAYILAN = {"h1": "Skunk", "h2": "Crystall", "h3": "Pollem"}

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

siparisler = yukle(S_DOSYA, {})
konumlar   = yukle(K_DOSYA, {})
havuz      = yukle(H_DOSYA, HAVUZ_VARSAYILAN)

if not os.path.exists(H_DOSYA):
    kaydet(H_DOSYA, havuz)

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

def ilce_konumlari(il, ilce):
    """İlçedeki aktif (silinmemiş, fotoğraflı, ürünlü) konumlar."""
    return [k for k in konumlar.get(il, {}).get(ilce, [])
            if not k.get("silindi") and k.get("foto_id") and k.get("urun")]

def ilce_urunler(il, ilce):
    """
    İlçedeki aktif konumların ürünlerini topla.
    { urun_adi: { gram: fiyat, ... } }
    Aynı isimde ürün birleştirilir (tüm gramlar gösterilir).
    """
    sonuc = {}
    for k in ilce_konumlari(il, ilce):
        u = k["urun"]
        ad = u["ad"]
        if ad not in sonuc:
            sonuc[ad] = {}
        g = str(u["gram"])
        sonuc[ad][g] = u["fiyat"]
    return sonuc

def ilce_konum_bul(il, ilce, urun_ad, gram):
    """Belirtilen ürün+gram için ilk aktif konumu döner."""
    for k in konumlar.get(il, {}).get(ilce, []):
        if k.get("silindi"):
            continue
        u = k.get("urun", {})
        if u.get("ad") == urun_ad and str(u.get("gram")) == str(gram):
            return k
    return None

def ilce_konum_sayisi(il, ilce):
    return len(ilce_konumlari(il, ilce))

# ─── MÜŞTERİ AKIŞI ───────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    aktif = [il for il, ilceler in konumlar.items()
             if any(ilce_konum_sayisi(il, ilce) > 0 for ilce in ilceler)]
    if not aktif:
        await update.message.reply_text(
            "Su an hizmet verilen bolge yok.\nLutfen daha sonra tekrar deneyin."
        )
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
    aktif_ilceler = [ilce for ilce in konumlar.get(il, {})
                     if ilce_konum_sayisi(il, ilce) > 0]
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
    kb = [[InlineKeyboardButton(f"🍬 {ad}", callback_data=f"urun:{ad}")]
          for ad in urunler.keys()]
    kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_il")])
    kb.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
    await q.edit_message_text(
        f"Il: {il}  |  Bolge: {ilce}\n\nUrun secin:",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    return URUN

async def urun_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "iptal":
        await q.edit_message_text("Iptal edildi.")
        return ConversationHandler.END
    if q.data == "geri_il":
        il = context.user_data["il"]
        aktif_ilceler = [ilce for ilce in konumlar.get(il, {})
                         if ilce_konum_sayisi(il, ilce) > 0]
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
    kb = [[InlineKeyboardButton(f"{g}  —  {fiyat_str(f)}",
                                callback_data=f"gram:{g}:{f}")]
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
        kb = [[InlineKeyboardButton(f"🍬 {ad}", callback_data=f"urun:{ad}")] for ad in urunler.keys()]
        kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_il")])
        kb.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
        await q.edit_message_text("Urun secin:", reply_markup=InlineKeyboardMarkup(kb))
        return URUN
    p    = q.data.split(":")
    gram = p[1]
    fiyat = float(p[2])
    context.user_data["gram"]  = gram
    context.user_data["fiyat"] = fiyat
    il      = context.user_data["il"]
    ilce    = context.user_data["ilce"]
    urun_ad = context.user_data["urun_ad"]
    no      = sp_no(update.effective_user.id)
    context.user_data["no"] = no
    ozet = (
        f"Siparis Ozeti\n─────────────────\n"
        f"Siparis No : {no}\n"
        f"Il         : {il}\n"
        f"Bolge      : {ilce}\n"
        f"Urun       : {urun_ad}\n"
        f"Miktar     : {gram}\n"
        f"Fiyat      : {fiyat_str(fiyat)}\n"
        f"─────────────────\n\n{BANKA}\n\n"
        f"Odemeyi yaptiktan sonra dekont fotografini gonderin."
    )
    kb = [
        [InlineKeyboardButton("✅ Siparisi Onayla", callback_data="onayla")],
        [InlineKeyboardButton("⬅️ Geri",            callback_data="geri_gram")],
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
    if q.data == "geri_gram":
        il      = context.user_data["il"]
        ilce    = context.user_data["ilce"]
        urun_ad = context.user_data["urun_ad"]
        urunler = ilce_urunler(il, ilce)
        gramlar = urunler.get(urun_ad, {})
        kb = [[InlineKeyboardButton(f"{g}  —  {fiyat_str(f)}",
                                    callback_data=f"gram:{g}:{f}")]
              for g, f in gramlar.items()]
        kb.append([InlineKeyboardButton("⬅️ Geri", callback_data="geri_ilce")])
        kb.append([InlineKeyboardButton("❌ Iptal", callback_data="iptal")])
        await q.edit_message_text("Miktar secin:", reply_markup=InlineKeyboardMarkup(kb))
        return GRAM
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
            "durum":   "beklemede"
        }
        kaydet(S_DOSYA, siparisler)
        await q.edit_message_text(
            f"Siparisıniz alindi!\n\nSiparis No: {no}\n\n"
            f"Havale/EFT islemini yapip dekontu gonderin.\n\nTesekkurler!"
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
                il      = s.get("il", "?")
                ilce    = s.get("ilce", "?")
                urun_ad = s.get("urun_ad", urun_ad)
                gram    = s.get("gram", gram)
                fiyat_v = s.get("fiyat", 0)
                break

    if not no:
        await update.message.reply_text("Aktif siparisıniz yok. /start ile baslayin.")
        return

    if no not in siparisler:
        siparisler[no] = {
            "user_id": uid,
            "il":      il,
            "ilce":    ilce,
            "urun":    f"{urun_ad} {gram}",
            "urun_ad": urun_ad,
            "gram":    gram,
            "fiyat":   fiyat_v,
            "durum":   "beklemede"
        }

    kb = [[InlineKeyboardButton(f"✅ Onayla — {no}", callback_data=f"onay:{no}")]]
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=update.message.photo[-1].file_id,
        caption=(
            f"Yeni Dekont!\n\n"
            f"No: {no}\n"
            f"Il/Ilce: {il}/{ilce}\n"
            f"Urun: {urun_ad} {gram}\n"
            f"Fiyat: {fiyat_str(fiyat_v)}\n\n"
            f"Onaylamak icin butona bas:"
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
    yeni = {
        "id":      k_id(),
        "lat":     lat,
        "lon":     lon,
        "foto_id": foto_id,
        "silindi": False,
        "urun":    {}
    }
    if il not in konumlar:
        konumlar[il] = {}
    if ilce not in konumlar[il]:
        konumlar[il][ilce] = []
    konumlar[il][ilce].append(yeni)
    kaydet(K_DOSYA, konumlar)
    kidx = len(konumlar[il][ilce]) - 1
    adm[uid] = {"adim": "urun_sec", "il": il, "ilce": ilce, "kidx": kidx}
    # Ürün havuzunu göster
    kb = [[InlineKeyboardButton(f"🍬 {ad}", callback_data=f"hs:{hid}:{il}:{ilce}:{kidx}")]
          for hid, ad in havuz.items()]
    kb.append([InlineKeyboardButton("➕ Yeni Urun Ekle", callback_data=f"hu:{il}:{ilce}:{kidx}")])
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

    # Havuzdan ürün seç
    if d.startswith("hs:"):
        p    = d.split(":")
        hid  = p[1]
        il   = p[2]
        ilce = p[3]
        kidx = int(p[4])
        adm[ADMIN_ID] = {
            "adim": "gram", "il": il, "ilce": ilce,
            "kidx": kidx, "urun_ad": havuz[hid]
        }
        await q.edit_message_text(f"Urun: {havuz[hid]}\n\nGram miktarini yaz (örn: 1g, 3.5g, 7g):")

    # Yeni ürün
    elif d.startswith("hu:"):
        p    = d.split(":")
        il   = p[1]
        ilce = p[2]
        kidx = int(p[3])
        adm[ADMIN_ID] = {"adim": "yeni_urun", "il": il, "ilce": ilce, "kidx": kidx}
        await q.edit_message_text("Yeni urun adini yaz:")

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
            await q.edit_message_caption(
                f"{il}/{ilce} bolgesinde bu urun icin musait konum kalmadi!\n"
                f"/konum_ekle ile yeni konum ekleyin."
            )
            return
        siparisler[no]["durum"] = "isleniyor"
        kaydet(S_DOSYA, siparisler)
        mid = s["user_id"]
        await context.bot.send_photo(
            chat_id=mid, photo=k["foto_id"],
            caption=f"Siparisıniz hazirlandi!\n\nSiparis No: {no}\nAsagidaki konumdan teslim alabilirsiniz."
        )
        await context.bot.send_location(chat_id=mid, latitude=k["lat"], longitude=k["lon"])
        await context.bot.send_message(
            chat_id=mid,
            text=f"Siparisıniz teslimata hazir!\n\nSiparis No: {no}\n\nIyi gunler!"
        )
        # Konumu sil
        for km in konumlar.get(il, {}).get(ilce, []):
            if km["id"] == k["id"]:
                km["silindi"] = True
                break
        kaydet(K_DOSYA, konumlar)
        siparisler[no]["durum"] = "tamamlandi"
        kaydet(S_DOSYA, siparisler)
        kalan = ilce_konum_sayisi(il, ilce)
        uyari = f"\n\n{il}/{ilce} bolgesinde {kalan} konum kaldi!" if kalan <= 3 else ""
        await q.edit_message_caption(f"Tamamlandi! {no}{uyari}")

    elif d == "tamam":
        await q.edit_message_text("Tamamlandi! /konum_ekle ile yeni konum ekleyebilirsin.")

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

        elif a["adim"] == "yeni_urun":
            hid = f"h{int(time.time())}"
            havuz[hid] = txt
            kaydet(H_DOSYA, havuz)
            adm[uid].update({"adim": "gram", "urun_ad": txt})
            await update.message.reply_text(f"Urun '{txt}' eklendi!\n\nGram miktarini yaz (örn: 1g):")
            return

        elif a["adim"] == "gram":
            a["gecici_gram"] = txt
            a["adim"]        = "fiyat"
            await update.message.reply_text(f"{txt} icin fiyati yaz:")
            return

        elif a["adim"] == "fiyat":
            try:
                f    = float(txt.replace(",", "."))
                g    = a["gecici_gram"]
                il   = a["il"]
                ilce = a["ilce"]
                kidx = a["kidx"]
                urun_ad = a["urun_ad"]
                # Konuma ürün bilgisini kaydet
                konumlar[il][ilce][kidx]["urun"] = {
                    "ad":    urun_ad,
                    "gram":  g,
                    "fiyat": f
                }
                kaydet(K_DOSYA, konumlar)
                del adm[uid]
                kalan = ilce_konum_sayisi(il, ilce)
                kb = [
                    [InlineKeyboardButton("📍 Ayni Ilceye Yeni Konum", callback_data=f"yeni_k:{il}:{ilce}")],
                    [InlineKeyboardButton("✅ Tamamlandi",              callback_data="tamam")],
                ]
                await update.message.reply_text(
                    f"Kaydedildi!\n\n"
                    f"Il: {il} / Ilce: {ilce}\n"
                    f"Urun: {urun_ad}\n"
                    f"Miktar: {g}\n"
                    f"Fiyat: {fiyat_str(f)}\n\n"
                    f"Bu ilcede {kalan} aktif konum var.",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
            except ValueError:
                await update.message.reply_text("Gecersiz fiyat! Sayi gir (örn: 150)")
            return

        elif a["adim"] == "havuz_ekle":
            hid = f"h{int(time.time())}"
            havuz[hid] = txt
            kaydet(H_DOSYA, havuz)
            del adm[uid]
            await update.message.reply_text(f"'{txt}' havuza eklendi!")
            return

    await update.message.reply_text("Siparis vermek icin /start yazin.")

# ─── ADMİN CALLBACK (konum ekle + havuz) ─────────────────────────────────────
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
        il     = d.split(":", 1)[1]
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

    elif d.startswith("yeni_k:"):
        p    = d.split(":")
        il   = p[1]
        ilce = p[2]
        adm[ADMIN_ID] = {"adim": "foto", "il": il, "ilce": ilce}
        await q.edit_message_text(f"{il}/{ilce} icin yeni konum.\n\nFotografi gonder:")

async def havuz_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        await q.answer("Yetkisiz!", show_alert=True)
        return
    await q.answer()
    d = q.data

    if d == "h_ekle":
        adm[ADMIN_ID] = {"adim": "havuz_ekle"}
        await q.edit_message_text("Yeni urun adini yaz:")

    elif d.startswith("h_sil:"):
        hid = d.split(":")[1]
        ad  = havuz.pop(hid, "")
        kaydet(H_DOSYA, havuz)
        kb = [[InlineKeyboardButton(f"🍬 {a}  🗑", callback_data=f"h_sil:{h}")] for h, a in havuz.items()]
        kb.append([InlineKeyboardButton("➕ Yeni Urun Ekle", callback_data="h_ekle")])
        await q.edit_message_text(
            f"'{ad}' silindi!\n\nUrun Havuzu:",
            reply_markup=InlineKeyboardMarkup(kb) if havuz else None
        )

# ─── KOMUTLAR ────────────────────────────────────────────────────────────────
async def konum_ekle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    iller = list(konumlar.keys())
    kb    = [[InlineKeyboardButton(f"📍 {il}", callback_data=f"ke_il:{il}")] for il in iller]
    kb.append([InlineKeyboardButton("➕ Yeni Il", callback_data="ke_yeni_il")])
    await update.message.reply_text("Il sec:", reply_markup=InlineKeyboardMarkup(kb))

async def urunler_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    kb = [[InlineKeyboardButton(f"🍬 {ad}  🗑", callback_data=f"h_sil:{hid}")] for hid, ad in havuz.items()]
    kb.append([InlineKeyboardButton("➕ Yeni Urun Ekle", callback_data="h_ekle")])
    await update.message.reply_text(
        "Urun Havuzu\n─────────────────\nSilmek icin uzerine tikla:",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def konumlar_goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not konumlar:
        await update.message.reply_text("Hic konum yok. /konum_ekle ile ekle.")
        return
    msg = "Konum Durumu\n─────────────────\n"
    for il, ilceler in konumlar.items():
        msg += f"\n📍 {il}\n"
        for ilce, liste in ilceler.items():
            kalan = ilce_konum_sayisi(il, ilce)
            e = "🟢" if kalan > 3 else ("🟡" if kalan > 0 else "🔴")
            msg += f"  {e} {ilce}: {kalan} aktif / {len(liste)} toplam\n"
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
            IL:    [CallbackQueryHandler(il_sec)],
            ILCE:  [CallbackQueryHandler(ilce_sec)],
            URUN:  [CallbackQueryHandler(urun_sec)],
            GRAM:  [CallbackQueryHandler(gram_sec)],
            ODEME: [CallbackQueryHandler(odeme)],
        },
        fallbacks=[CommandHandler("iptal", iptal)],
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("siparisler", siparisler_goster))
    app.add_handler(CommandHandler("konumlar",   konumlar_goster))
    app.add_handler(CommandHandler("konum_ekle", konum_ekle))
    app.add_handler(CommandHandler("urunler",    urunler_goster))
    app.add_handler(CallbackQueryHandler(adm_cb,   pattern=r"^(hs:|hu:|onay:|tamam)"))
    app.add_handler(CallbackQueryHandler(ke_cb,    pattern=r"^(ke_|yeni_k:)"))
    app.add_handler(CallbackQueryHandler(havuz_cb, pattern=r"^h_"))
    app.add_handler(MessageHandler(filters.PHOTO,    foto_al))
    app.add_handler(MessageHandler(filters.LOCATION, konum_al))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, metin))
    logger.info(f"Bot basladi. Siparis:{len(siparisler)} Havuz:{len(havuz)}")
    app.run_polling()

if __name__ == "__main__":
    main()
