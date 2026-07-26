from db.database import get_connection

conn = get_connection()
cur = conn.cursor()

# Doğru sütun adlarıyla arama yapıyoruz
cur.execute("""
    SELECT kaynak, icerik 
    FROM dokuman_chunklari 
    WHERE kaynak LIKE '%majezik%' OR icerik LIKE '%majezik%'
    LIMIT 3
""")

rows = cur.fetchall()
if not rows:
    print("UYARI: Veritabanında 'majezik' kelimesi içeren hiçbir chunk bulunamadı!")
else:
    for r in rows:
        print("--- BULUNAN VERİ ---")
        print("Kaynak Dosya:", r[0])
        print("İçerik (İlk 400 karakter):", r[1][:400])

conn.close()