import os
import sys

# Ana kök dizini sabitleyelim (Çalışma dizini hatalarını önlemek için)
BASE_DIR = r"C:\Users\Mert Cihan\OneDrive - isik.edu.tr\Masaüstü\ClinicaAI"
sys.path.append(BASE_DIR)

import pandas as pd
from db.database import get_connection

def semptom_brans_yukle():
    csv_yolu = os.path.join(BASE_DIR, "data", "semptom_brans", "Semptom-Brans Eslesme Tablosu.csv")
    
    if not os.path.exists(csv_yolu):
        print(f"⚠️ Dosya bulunamadı: {csv_yolu}")
        return

    df = pd.read_csv(csv_yolu)
    conn = get_connection()
    cur = conn.cursor()

    # EMNİYET KİLİDİ: Tablo veritabanında yoksa otomatik oluşturur
    cur.execute("""
        CREATE TABLE IF NOT EXISTS semptom_brans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            semptom TEXT,
            brans TEXT
        )
    """)

    # Önce eski verileri temizle (tekrar çalıştırırsak duplicate olmasın)
    cur.execute("DELETE FROM semptom_brans")

    toplam = 0
    for _, satir in df.iterrows():
        semptom_listesi = str(satir['Semptom']).split(',')
        brans = str(satir['İlgili Branş']).strip()

        for semptom in semptom_listesi:
            semptom_temiz = semptom.strip()
            if semptom_temiz:
                cur.execute(
                    "INSERT INTO semptom_brans (semptom, brans) VALUES (?, ?)",
                    (semptom_temiz, brans)
                )
                toplam += 1

    conn.commit()
    conn.close()
    print(f"{toplam} semptom-brans eşleşmesi başarıyla yüklendi!")

if __name__ == "__main__":
    semptom_brans_yukle()
    