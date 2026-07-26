import os
import sys

BASE_DIR = r"C:\Users\Mert Cihan\OneDrive - isik.edu.tr\Masaüstü\ClinicaAI"
sys.path.append(BASE_DIR)

from db.database import get_connection
from sentence_transformers import SentenceTransformer

print("Model yükleniyor...")
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

def test_et():
    conn = get_connection()
    cur = conn.cursor()
    
    # 1. Tabloda kayıt var mı kontrol et
    cur.execute("SELECT COUNT(*) FROM dokuman_chunklari")
    toplam = cur.fetchone()[0]
    print(f"Veritabanındaki toplam chunk sayısı: {toplam}")
    
    if toplam == 0:
        print("❌ HATA: Veritabanı boş! `ingest.py` dosyasını tekrar çalıştırmalısın.")
        return

    # 2. Majezik kelimesini direkt veritabanında arayalım
    cur.execute("SELECT kaynak, icerik FROM dokuman_chunklari WHERE icerik LIKE '%Majezik%' LIMIT 2")
    sonuclar = cur.fetchall()
    
    if sonuclar:
        print("\n✅ DOĞRUDAN SQL İLE BULUNDU:")
        for kaynak, icerik in sonuclar:
            print(f"- Kaynak: {kaynak}")
            print(f"- İçerik özeti: {icerik[:150]}...\n")
    else:
        print("\n❌ UYARI: 'Majezik' kelimesi veritabanında direkt metin olarak geçmiyor.")
        
    conn.close()

if __name__ == "__main__":
    test_et()
    