import sqlite3
import pandas as pd
from geopy.geocoders import Nominatim
import time
from tqdm import tqdm

print("Veritabanı okunuyor...")
import os
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hastaneler.db")
conn = sqlite3.connect(DB_PATH)

# Sadece var olan sütunları çekiyoruz (id hatası giderildi)
df = pd.read_sql_query("SELECT isim, il, ilce, enlem, boylam FROM hastaneler", conn)

geolocator = Nominatim(user_agent="saglik_asistani_projesi")
print("Eksik adresler harita üzerinden bulunuyor. (Bu işlem biraz sürebilir...)")

for index, row in tqdm(df.iterrows(), total=df.shape[0]):
    if row['il'] == 'Bilinmiyor' or row['ilce'] == 'Bilinmiyor':
        try:
            location = geolocator.reverse((row['enlem'], row['boylam']), exactly_one=True, timeout=10)
            if location and location.raw.get('address'):
                address = location.raw['address']
                il = address.get('province', address.get('city', address.get('state', 'Bilinmiyor')))
                ilce = address.get('town', address.get('district', address.get('county', 'Bilinmiyor')))
                df.at[index, 'il'] = il
                df.at[index, 'ilce'] = ilce
            time.sleep(1) 
        except Exception as e:
            pass

print("Güncellenmiş veriler kaydediliyor...")
df.to_sql('hastaneler', conn, if_exists='replace', index=False)
conn.close()
print("İşlem tamam!")
