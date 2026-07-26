import sqlite3
import sqlite_vec

def get_connection():
    conn = sqlite3.connect('hastaneler.db')
    conn.isolation_level = None  # otomatik commit modu
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS dokuman_chunklari (
        id INTEGER PRIMARY KEY,
        doc_type TEXT,
        kaynak TEXT,
        icerik TEXT
    )
    """)
    print("dokuman_chunklari tablosu tamam.")

    try:
        cur.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunklari USING vec0(
            chunk_id INTEGER PRIMARY KEY,
            embedding FLOAT[384]
        )
        """)
        print("vec_chunklari tablosu tamam.")
    except Exception as e:
        print("HATA - vec_chunklari olusturulamadi:", e)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS semptom_brans (
        id INTEGER PRIMARY KEY,
        semptom TEXT,
        brans TEXT
    )
    """)
    print("semptom_brans tablosu tamam.")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS ilaclar (
        id INTEGER PRIMARY KEY,
        ilac_adi TEXT,
        etken_madde TEXT,
        yan_etkiler TEXT,
        kullanim_sekli TEXT
    )
    """)
    print("ilaclar tablosu tamam.")

    conn.close()

if __name__ == "__main__":
    init_db()
    print("Islem bitti.")
    