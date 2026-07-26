import os
import re

KLASOR = r"C:\Users\Mert Cihan\OneDrive - isik.edu.tr\Masaüstü\ClinicaAI\data\ilaclar"

# UUID formatını yakalayan regex: _xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
uuid_pattern = re.compile(r'_[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')

for dosya_adi in os.listdir(KLASOR):
    if not dosya_adi.endswith('.pdf'):
        continue
    yeni_ad = uuid_pattern.sub('', dosya_adi)
    if yeni_ad != dosya_adi:
        eski_yol = os.path.join(KLASOR, dosya_adi)
        yeni_yol = os.path.join(KLASOR, yeni_ad)
        print(f"{dosya_adi}  -->  {yeni_ad}")
        os.rename(eski_yol, yeni_yol)

print("Bitti.")
