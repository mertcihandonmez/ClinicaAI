import os
import re
import sqlite3
import openai
import pandas as pd
import streamlit as st
import sys

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"  # GPU'yu tamamen kapatıp işlemciye (CPU) zorlar
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db.database import get_connection

# Sayfa ayarları
st.set_page_config(page_title="Sağlık AI Asistanı", layout="wide")

# --- Embedding modelini bir kere yükle ---
@st.cache_resource
def embedding_modeli_yukle():
  from sentence_transformers import SentenceTransformer

  return SentenceTransformer(
      "paraphrase-multilingual-MiniLM-L12-v2", local_files_only=True
  )


embed_model = embedding_modeli_yukle()
@st.cache_resource
def foundry_baglantisi_kur():
    return openai.OpenAI(base_url="http://127.0.0.1:52620/v1", api_key="none")

foundry_client = foundry_baglantisi_kur()

# --- Hasta Modu: semptom -> branş arama ---
def semptom_brans_ara(mesaj):
    try:
        conn = sqlite3.connect("hastaneler.db")
        cur = conn.cursor()
        cur.execute("SELECT semptom, brans FROM semptom_brans")
        tum_kayitlar = cur.fetchall()
        conn.close()
    except Exception:
        return []

    mesaj_kucuk = mesaj.lower()
    genel_kelimeler = {
        "ağrı", "ağrısı", "ağrıyor", "sürekli", "var", "bulunması",
        "şikayeti", "problemi", "sorunu", "hissi", "durumu",
    }

    def kok_bul(kelime):
        for ek in ["ları", "leri", "ının", "inin", "ımın", "imin",
                   "sının", "sinin", "ım", "im", "sı", "si",
                   "ıyor", "iyor"]:
            if kelime.endswith(ek) and len(kelime) - len(ek) >= 3:
                return kelime[:-len(ek)]
        return kelime

    eslesme_skorlari = {}

    for semptom, brans in tum_kayitlar:
        semptom_kelimeleri = semptom.lower().split()
        for kelime in semptom_kelimeleri:
            if kelime in genel_kelimeler or len(kelime) < 3:
                continue
            semptom_koku = kok_bul(kelime)

            for mesaj_kelimesi in mesaj_kucuk.split():
                mesaj_koku = kok_bul(mesaj_kelimesi)
                if len(semptom_koku) >= 3 and semptom_koku == mesaj_koku:
                    eslesme_skorlari[brans] = eslesme_skorlari.get(brans, 0) + 1
                    break

    if not eslesme_skorlari:
        return []

    max_skor = max(eslesme_skorlari.values())
    en_iyi_branslar = [b for b, skor in eslesme_skorlari.items() if skor == max_skor]
    return en_iyi_branslar


# --- İlaç Tespiti ve Konum Filtreleme Fonksiyonları ---
def ilac_talebi_tespit(mesaj):
  kaliplar = [
      r"doktor.*yazdı",
      r"doktorum.*yazdı",
      r"reçete.*yazıldı",
      r"ilaç.*yazdı",
      r"kullanmam[ıi] söyledi",
      r"almam[ıi] söyledi",
      r"reçete edildi",
  ]
  mesaj_kucuk = mesaj.lower()
  return any(re.search(k, mesaj_kucuk) for k in kaliplar)


def ilac_ismi_cikar(mesaj):
  kelimeler = mesaj.split()
  for i, k in enumerate(kelimeler):
    if k.lower() in ("yazdı", "yazıldı", "verdi") and i > 0:
      return kelimeler[i - 1].strip(".,!?")
  return None


def ilac_sorusu_mu(mesaj):
  anahtar_kelimeler = [
      "yan etki",
      "ne için kullan",
      "ne işe yarar",
      "doz",
      "kullanım şekli",
      "ilacı",
      "ilaç mı",
  ]
  mesaj_kucuk = mesaj.lower()
  return any(a in mesaj_kucuk for a in anahtar_kelimeler)


def en_yakin_hastaneler(il_ilce_metni, hastane_df, limit=5):
  if hastane_df.empty:
    return hastane_df

  temiz_metin = il_ilce_metni.split(",")[0].lower().strip()

  # .str.contains kullanarak tam eşleşme yerine kelimeyi içerenleri (partial match) alıyoruz
  ilce_eslesen = hastane_df[
      hastane_df["ilce"].str.lower().str.contains(temiz_metin, na=False)
  ]
  if not ilce_eslesen.empty:
    return ilce_eslesen.head(limit)

  il_eslesen = hastane_df[
      hastane_df["il"].str.lower().str.contains(temiz_metin, na=False)
  ]
  if not il_eslesen.empty:
    return il_eslesen.head(limit)

  # Hiçbiri olmazsa hastane isminde bile geçiyorsa yakalasın (Örn: Üsküdar Devlet Hastanesi gibi)
  isim_eslesen = hastane_df[
      hastane_df["isim"].str.lower().str.contains(temiz_metin, na=False)
  ]
  return isim_eslesen.head(limit)

def dokuman_ara(sorgu_metni, k=3):
    try:
        conn = get_connection()
        cur = conn.cursor()

        sorgu_embedding = embed_model.encode(sorgu_metni).tolist()

        cur.execute("""
            SELECT dc.kaynak, dc.icerik, v.distance
            FROM vec_chunklari v
            JOIN dokuman_chunklari dc ON v.chunk_id = dc.id
            WHERE v.embedding MATCH ? AND k = ?
            ORDER BY v.distance
        """, (str(sorgu_embedding), k))

        sonuclar = cur.fetchall()
        conn.close()

        gorulmus = set()
        benzersiz_sonuclar = []
        for kaynak, icerik, mesafe in sonuclar:
            if icerik not in gorulmus:
                gorulmus.add(icerik)
                benzersiz_sonuclar.append((kaynak, icerik, mesafe))
        return benzersiz_sonuclar
    except Exception as e:
        print(f"Arama hatası: {e}")
        return []


# --- Klinik Modu: Düzeltilmiş Vektör Arama ---
def ilac_adi_ile_ara(mesaj, k=4):
    """Once mesajdaki kelimeleri dogrudan PDF dosya adinda arar, o dosyadan birden fazla parca doner."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        kelimeler = [w.strip(".,!?'") for w in mesaj.lower().split() if len(w.strip(".,!?'")) > 3]

        for kelime in kelimeler:
            cur.execute("""
                SELECT kaynak, icerik, 0.0 as distance
                FROM dokuman_chunklari
                WHERE LOWER(kaynak) LIKE ?
                LIMIT ?
            """, (f"%{kelime}%", k))
            sonuc = cur.fetchall()
            if sonuc:
                conn.close()
                return sonuc

        conn.close()
        return []
    except Exception:
        return []

from difflib import SequenceMatcher

def tekrar_temizle(metin, esik=0.6):
    """Anlamca birbirine çok benzeyen (paraphrase) cümleleri de yakalayıp keser."""
    cumleler = re.split(r'(?<=[.!?])\s+', metin.strip())
    temiz = []
    for c in cumleler:
        c_str = c.strip()
        if not c_str:
            continue
        benzer_var_mi = any(
            SequenceMatcher(None, c_str.lower(), onceki.lower()).ratio() > esik
            for onceki in temiz
        )
        if benzer_var_mi:
            break
        temiz.append(c_str)
    return " ".join(temiz)

def yarim_cumle_kirp(metin):
    """Nokta/soru/ünlem ile bitmeyen son parçayı atar."""
    if metin and metin[-1] not in ".!?":
        son_nokta = max(metin.rfind("."), metin.rfind("!"), metin.rfind("?"))
        if son_nokta > 0:
            return metin[:son_nokta + 1]
    return metin

def gereksiz_uyari_temizle(metin):
    """Kaynak zaten bulunmusken sona eklenen 'bilgim yok' cumlesini kaldirir."""
    kaliplar = [
        r"\s*Bu konuda elimde yeterli bilgi yok[,.]?\s*(eczacınıza danışınız)?\.?\s*$",
        r"\s*Bu konuda yeterli bilgim yok\.?\s*$",
    ]
    for k in kaliplar:
        metin = re.sub(k, "", metin, flags=re.IGNORECASE)
    return metin.strip()



def model_cevabi_al(mesaj, mod):
    baglam_parcalari = []
    kaynak_bilgisi = []

    if mod == "Hasta Modu (Yönlendirme)":
        branslar = semptom_brans_ara(mesaj)

        # Ilac sorusu degilse ve brans bulunduysa, LLM'e sormadan direkt cevap ver
        if branslar and not ilac_sorusu_mu(mesaj):
            cevap = (
                f"Belirttiğiniz şikayetler doğrultusunda başvurabileceğiniz "
                f"ilgili poliklinik(ler): **{', '.join(branslar)}**.\n\n"
                f"Kesin teşhis için lütfen bir sağlık kuruluşuna başvurunuz."
            )
            return cevap, branslar

        # Ilac sorusuysa doküman ara ve modele sor
        if ilac_sorusu_mu(mesaj):
            sonuclar = ilac_adi_ile_ara(mesaj, k=4)
            if not sonuclar:
                sonuclar = dokuman_ara(mesaj, k=2)
            for kaynak, icerik, _ in sonuclar:
                baglam_parcalari.append(icerik)
                kaynak_bilgisi.append(kaynak)

    else:
        sonuclar = dokuman_ara(mesaj, k=2)
        for kaynak, icerik, _ in sonuclar:
            baglam_parcalari.append(icerik)
            kaynak_bilgisi.append(kaynak)

    if not baglam_parcalari:
        if mod == "Hasta Modu (Yönlendirme)":
            return (
                "Belirttiğiniz şikayetler için net bir bölüm tespit edemedim. "
                "Lütfen semptomlarınızı biraz daha detaylandırabilir misiniz?",
                [],
            )
        return (
            "Yerel veritabanımdaki dokümanlarda bu soruyla doğrudan eşleşen bir "
            "bilgi bulamadım. Lütfen sorunuzu daha net belirterek tekrar sorabilirsin.",
            [],
        )

    baglam = "\n---\n".join(baglam_parcalari)

    sistem_mesaji = (
        "Sen profesyonel bir tıbbi asistan ve metin özetleme uzmanısın. "
        "Görevin, aşağıda sağlanan 'BAĞLAM' bilgisini kullanarak kullanıcının sorusunu net, "
        "akıcı ve tıbbi olarak doğru bir Türkçe ile yanıtlamaktır.\n\n"
        "KESİN KURALLARIN:\n"
        "1. Asla aynı kelimeyi, heceyi veya cümleyi ard arda tekrarlama (kelime döngüsüne girme).\n"
        "2. SADECE sağlanan bağlamdaki bilgiyi kullan, dışarıdan bilgi uydurma.\n"
        "3. Bağlamda net bir yanıt yoksa, kendi kendine kelime üretmek yerine açıkça "
        "'Bu konuda elimde yeterli bilgi yok' de.\n"
        "4. Cümleleri mantıklı bir akışla, maddeler halinde düzenli bir şekilde yaz.\n\n"
        f"BAĞLAM:\n{baglam}"
    )


    messages = [
        {"role": "system", "content": sistem_mesaji},
        {"role": "user", "content": mesaj},
    ]

    try:
        response = foundry_client.chat.completions.create(
            model="phi-4-mini",
            messages=messages,
            temperature=0.5,
            max_tokens=280,
            frequency_penalty=1.0,
            presence_penalty=1.0,
            extra_body={"repetition_penalty": 1.3},
        )


        cevap = response.choices[0].message.content
        cevap = tekrar_temizle(cevap)
        cevap = yarim_cumle_kirp(cevap)
        if kaynak_bilgisi:
            cevap = gereksiz_uyari_temizle(cevap)
            

    except Exception as e:
        cevap = f"Model yanıt üretirken bir hata oluştu: {e}"

    return cevap, list(set(kaynak_bilgisi))

# Veritabanından hastaneleri okuma
def hastaneleri_getir():
  try:
    conn = sqlite3.connect("hastaneler.db")
    df = pd.read_sql_query(
        "SELECT isim, il, ilce, enlem, boylam FROM hastaneler WHERE enlem IS NOT"
        " NULL",
        conn,
    )
    conn.close()
    return df
  except Exception:
    return pd.DataFrame(columns=["isim", "il", "ilce", "enlem", "boylam"])


# Sohbet geçmişi ve To-Do listesini başlatma
if "mesajlar" not in st.session_state:
  st.session_state.mesajlar = []
if "son_kaynaklar" not in st.session_state:
  st.session_state.son_kaynaklar = []
if "ilac_listesi" not in st.session_state:
  st.session_state.ilac_listesi = []

# Arayüz Tasarımı
st.title("Dual-Mode Yerel Sağlık Asistanı")

# Sol Panel (To-Do & Kontrol)
with st.sidebar:
  st.header("⚙️ Kontrol Paneli")
  secilen_mod = st.radio(
      "Asistan Modunu Seçin:",
      ["Hasta Modu (Yönlendirme)", "Klinik Asistan (RAG)"],
  )
  st.divider()

  st.header("💊 İlaçlarım (To-Do)")
  if not st.session_state.ilac_listesi:
    st.info("Sohbet sırasında eklenen ilaçlar burada görünecek.")
  else:
    for idx, ilac in enumerate(st.session_state.ilac_listesi):
      with st.expander(f"💊 {ilac['ilac']}"):
        yeni_zaman = st.selectbox(
            "Ne zaman kullanılacak?",
            [
                "Seçilmedi",
                "Aç karnına",
                "Tok karnına",
                "Sabah",
                "Öğle",
                "Akşam",
                "Gece",
            ],
            index=0,
            key=f"zaman_{idx}",
        )
        yeni_not = st.text_input(
            "Not ekle", value=ilac["not"], key=f"not_{idx}"
        )
        st.session_state.ilac_listesi[idx]["zaman"] = yeni_zaman
        st.session_state.ilac_listesi[idx]["not"] = yeni_not
        if st.button("Sil", key=f"sil_{idx}"):
          st.session_state.ilac_listesi.pop(idx)
          st.rerun()

  manuel_ilac = st.text_input("Manuel ilaç ekle:")
  if st.button("Ekle") and manuel_ilac:
    st.session_state.ilac_listesi.append(
        {"ilac": manuel_ilac, "zaman": "", "not": ""}
    )
    st.rerun()

  st.divider()
  if st.button("Sohbeti Temizle"):
    st.session_state.mesajlar = []
    st.session_state.son_kaynaklar = []
    st.rerun()

# Ana Ekran
col1, col2 = st.columns([1, 1])

with col1:
  st.subheader("💬 Sohbet Asistanı")

  for mesaj in st.session_state.mesajlar:
    with st.chat_message(mesaj["rol"]):
      st.markdown(mesaj["icerik"])

  if kullanici_girdisi := st.chat_input(
      "Semptomlarınızı veya sorunuzu yazın..."
  ):
    st.session_state.mesajlar.append(
        {"rol": "user", "icerik": kullanici_girdisi}
    )
    with st.chat_message("user"):
      st.markdown(kullanici_girdisi)

    with st.chat_message("assistant"):
      if secilen_mod == "Hasta Modu (Yönlendirme)" and ilac_talebi_tespit(
          kullanici_girdisi
      ):
        ilac_adi = ilac_ismi_cikar(kullanici_girdisi) or "Bilinmeyen ilaç"
        
        # Mükerrer (aynı ilacın birden fazla eklenmesini) önleme kontrolü
        if not any(
            item["ilac"].lower() == ilac_adi.lower()
            for item in st.session_state.ilac_listesi
        ):
          st.session_state.ilac_listesi.append(
              {"ilac": ilac_adi, "zaman": "Seçilmedi", "not": ""}
          )
          
        cevap = (
            f"'{ilac_adi}' ilacınızı listeye ekledim. Sol paneldeki 'İlaçlarım'"
            " bölümünden aç/tok durumunu ve notlarınızı ekleyebilirsiniz."
        )
        st.markdown(cevap)
        st.session_state.mesajlar.append(
            {"rol": "assistant", "icerik": cevap}
        )
        
        # Sol panelin anında güncellenmesini sağlayan tetikleyici
        st.rerun()
        
      else:
        with st.spinner("Düşünüyor..."):
            sonuc = model_cevabi_al(kullanici_girdisi, secilen_mod)
            if isinstance(sonuc, tuple):
                cevap, kaynaklar = sonuc
            else:
                cevap, kaynaklar = sonuc, []
        st.markdown(cevap)

        st.session_state.mesajlar.append(
            {"rol": "assistant", "icerik": cevap}
        )
        st.session_state.son_kaynaklar = kaynaklar

with col2:
  if secilen_mod == "Hasta Modu (Yönlendirme)":
    st.subheader("🏥 Hastane Haritası ve Konum")
    if st.session_state.son_kaynaklar:
      st.success(
          f"Tespit edilen bölüm(ler): {', '.join(st.session_state.son_kaynaklar)}"
      )

    konum_girdisi = st.text_input(
        "Bulunduğunuz il/ilçeyi yazın (örn: Kadıköy, İstanbul):"
    )
    hastane_verisi = hastaneleri_getir()

    if konum_girdisi and not hastane_verisi.empty:
      gosterilecek_veri = en_yakin_hastaneler(konum_girdisi, hastane_verisi)
      if not gosterilecek_veri.empty:
        st.write(f"**{konum_girdisi} yakınındaki hastaneler:**")
        for _, satir in gosterilecek_veri.iterrows():
          st.write(f"- {satir['isim']} ({satir['ilce']}, {satir['il']})")
        harita_verisi = gosterilecek_veri.rename(
            columns={"enlem": "lat", "boylam": "lon"}
        )
        st.map(harita_verisi, zoom=11)
      else:
        st.warning("Bu bölgede hastane bulunamadı.")
    elif not hastane_verisi.empty:
      harita_verisi = hastane_verisi.rename(
          columns={"enlem": "lat", "boylam": "lon"}
      )
      st.map(harita_verisi, zoom=5)
    else:
      st.info("Harita verisi yükleniyor veya tablo boş.")
  else:
    st.subheader("📚 Medikal Kaynaklar (RAG)")
    if st.session_state.son_kaynaklar:
      st.write("**Kullanılan kaynaklar:**")
      for kaynak in set(st.session_state.son_kaynaklar):
        st.write(f"- {kaynak}")
    else:
      st.info("Sohbet ettikçe burada kullanılan kaynaklar görünecek.")
