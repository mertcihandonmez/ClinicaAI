import os
import sys
import pandas as pd
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
import sqlite_vec

# Bilgisayarındaki ana kök dizini ve data klasörünü doğrudan sabitleyelim
BASE_DIR = r"C:\Users\Mert Cihan\OneDrive - isik.edu.tr\Masaüstü\ClinicaAI"
DATA_DIR = os.path.join(BASE_DIR, "data")

sys.path.append(BASE_DIR)
from db.database import get_connection

print(f"Sabit Kök Dizin: {BASE_DIR}")
print(f"Sabit Veri Klasörü: {DATA_DIR}")

print("Embedding modeli yükleniyor...")
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

def pdf_metnini_cikar(pdf_yolu):
    reader = PdfReader(pdf_yolu)
    tam_metin = ""
    for sayfa in reader.pages:
        metin = sayfa.extract_text()
        if metin:
            tam_metin += metin + "\n"
    return tam_metin

def metni_parcala(metin, parca_boyutu=500, ortak_bolge=50):
    parcalar = []
    baslangic = 0
    while baslangic < len(metin):
        bitis = baslangic + parca_boyutu
        parcalar.append(metin[baslangic:bitis])
        baslangic += parca_boyutu - ortak_bolge
    return [p.strip() for p in parcalar if p.strip()]

def klasoru_isle(klasor_adi, doc_type):
  klasor_yolu = os.path.join(DATA_DIR, klasor_adi)
  if not os.path.exists(klasor_yolu):
    print(f"⚠️ Bulunamadı: {klasor_yolu}")
    return

  conn = get_connection()
  cur = conn.cursor()

  # os.walk kullanarak alt klasörlerin içindeki PDF'leri de bulalım
  for kok, alt_klasorler, dosyalar in os.walk(klasor_yolu):
    for dosya_adi in dosyalar:
      if not dosya_adi.endswith(".pdf"):
        continue
      print(f"İşleniyor ({doc_type}): {dosya_adi}")
      tam_yol = os.path.join(kok, dosya_adi)
      metin = pdf_metnini_cikar(tam_yol)
      parcalar = metni_parcala(metin)

      for parca in parcalar:
        cur.execute(
            "INSERT INTO dokuman_chunklari (doc_type, kaynak, icerik) VALUES"
            " (?, ?, ?)",
            (doc_type, dosya_adi, parca),
        )
        chunk_id = cur.lastrowid
        embedding = model.encode(parca).tolist()
        vector_blob = sqlite_vec.serialize_float32(embedding)
        cur.execute(
            "INSERT INTO vec_chunklari (chunk_id, embedding) VALUES (?, ?)",
            (chunk_id, vector_blob),
        )
  conn.commit()
  conn.close()
  
def ilaclari_isle(klasor_adi):
    klasor_yolu = os.path.join(DATA_DIR, klasor_adi)
    if not os.path.exists(klasor_yolu):
        print(f"⚠️ İlaç klasörü bulunamadı: {klasor_yolu}")
        return
    
    conn = get_connection()
    cur = conn.cursor()
    
    for dosya_adi in os.listdir(klasor_yolu):
        if not dosya_adi.endswith('.pdf'):
            continue
            
        print(f"İşleniyor (ilac): {dosya_adi}")
        tam_yol = os.path.join(klasor_yolu, dosya_adi)
        metin = pdf_metnini_cikar(tam_yol)
        
        # Dosya adından temiz bir ilaç ismi türetme (örn: ilac_majezik_kub.pdf -> majezik)
        temiz_ad = dosya_adi.replace('.pdf', '').replace('ilac_', '').replace('_kub', '').replace('_kt', '').replace('_', ' ').title()
        
        cur.execute(
            "INSERT INTO ilaclar (ilac_adi, etken_madde, yan_etkiler, kullanim_sekli) VALUES (?, ?, ?, ?)",
            (temiz_ad, "PDF İçeriği", metin[:1000], "KÜB/KT Dokümanı")
        )
        
        parcalar = metni_parcala(metin)
        for parca in parcalar:
            cur.execute(
                "INSERT INTO dokuman_chunklari (doc_type, kaynak, icerik) VALUES (?, ?, ?)",
                ("ilac", dosya_adi, parca)
            )
            chunk_id = cur.lastrowid
            embedding = model.encode(parca).tolist()
            vector_blob = sqlite_vec.serialize_float32(embedding)
            cur.execute(
                "INSERT INTO vec_chunklari (chunk_id, embedding) VALUES (?, ?)",
                (chunk_id, vector_blob)
            )
            
    conn.commit()
    conn.close()
    
def semptom_brans_isle(klasor_adi):
    klasor_yolu = os.path.join(DATA_DIR, klasor_adi)
    if not os.path.exists(klasor_yolu):
        print(f"⚠️ Semptom-branş klasörü bulunamadı: {klasor_yolu}")
        return
        
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM semptom_brans")

    # Klasörün içindeki dosyaları tarayalım (büyük/küçük harf veya boşluk duyarlılığını aşmak için)
    for dosya_adi in os.listdir(klasor_yolu):
        if dosya_adi.lower().endswith('.csv'):
            tam_csv_yolu = os.path.join(klasor_yolu, dosya_adi)
            print(f"İşleniyor (semptom-branş): {dosya_adi}")
            
            # Türkçe karakter veya farklı ayraç ihtimaline karşı encoding denemesi
            df = pd.read_csv(tam_csv_yolu, encoding='utf-8')
            
            for _, row in df.iterrows():
                # Semptom ve Branş sütun adlarının CSV'dekilerle birebir eşleştiğinden emin olalım
                semptom_listesi = str(row['Semptom']).split(',')
                brans = str(row['İlgili Branş']).strip()
                for semptom in semptom_listesi:
                    semptom_temiz = semptom.strip()
                    if semptom_temiz:
                        cur.execute("INSERT INTO semptom_brans (semptom, brans) VALUES (?, ?)",
                                     (semptom_temiz, brans))
    conn.commit()
    conn.close()
    print("Semptom-branş verileri başarıyla yüklendi!")

def tabolari_temizle():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM dokuman_chunklari")
    cur.execute("DELETE FROM vec_chunklari")
    cur.execute("DELETE FROM ilaclar")
    conn.commit()
    conn.close()
    print("Eski veriler temizlendi, yeniden yukleniyor...")

if __name__ == "__main__":
    from db.database import init_db
    init_db()   # Tabloları oluştur
    tabolari_temizle()
    klasoru_isle("klinik", "klinik")
    klasoru_isle("prosedur", "prosedur")
    klasoru_isle("ilkyardim", "ilkyardim")
    ilaclari_isle("ilaclar")
    semptom_brans_isle("semptom_brans")
    print("🎉 HER ŞEY BAŞARIYLA VERİTABANINA AKTARILDI!")
