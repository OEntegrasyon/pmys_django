# PMYS Django Backend

## Gereksinim
Python versiyon >= 3.10.12

## Kurulum
Sanal ortamı kurun:
```bash
python3 -m venv venv
source venv/bin/activate
```
Burası opsiyonel, pip ve wheel sürümlerini yükseltmek gerekirse:
```bash
pip install --upgrade pip
pip install --upgrade wheel
```
Paketleri kurun:
```bash
pip install -r requirements.txt
```

## Konfigürasyon
Öncelikle pmys dizini altındaki settings.py.template dosyası kopyalayıp adını settings.py yapın.
```bash
cp pmys/settins.py.template pmys/settings.py
```

settings.py içerisinde
- SECRET_KEY = 'secret_key'
- CORS_ALLOWED_ORIGINS = ["http://frontend_url:port",]

kısımlarını doldurun.

env_variables.sh içerisindeki ilgili kısımları doldurun ve uygulamayı başlatacağınız terminalde çalıştırın. Farklı bir terminalde çalıştırılsa işe yaramaz.

## Başlatmak İçin
Veri tabanını hazırlayın:
```bash
python manage.py makemigrations
python manage.py migrate
```

Uygulamayı başlatın
```bash
python manage.py runserver 0.0.0.0:8000
```