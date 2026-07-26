import pandas as pd
import sqlite3

# 1. Dosyayı doğru formatta (Tab ayrımıyla) oku
print("Dosya okunuyor...")
df = pd.read_csv('interpreter.csv', sep='\t')

# 2. Sütun isimlerini projeye uygun, temiz Türkçe isimlere çevir
df = df.rename(columns={
    '@lat': 'enlem',
    '@lon': 'boylam',
    'name': 'isim',
    'addr:city': 'il',
    'addr:district': 'ilce'
})

# 3. İsmi girilmemiş (haritaya yanlış eklenmiş) hatalı satırları sil
df = df.dropna(subset=['isim'])

# 4. İl ve ilçe kısmı boş bırakılan yerlere "Bilinmiyor" yaz
# (Önemli değil, elimizde enlem/boylam olduğu için haritada doğru yerde çıkacaklar)
df['il'] = df['il'].fillna('Bilinmiyor')
df['ilce'] = df['ilce'].fillna('Bilinmiyor')

# 5. Temizlenmiş veriyi SQLite veri tabanına kaydet
print("Veri tabanı oluşturuluyor...")
import os
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hastaneler.db")
conn = sqlite3.connect(DB_PATH)
df.to_sql('hastaneler', conn, if_exists='replace', index=False)
conn.close()

print("İşlem tamam! 'interpreter.csv' dosyası temizlenerek 'hastaneler.db' veri tabanına dönüştürüldü.")