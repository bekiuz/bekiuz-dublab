# Bekiuz DubLab 🎙️

AI yordamida anime dublyaj sahnasi va ovoz aktyorligini baholovchi Telegram bot.

## Bot qanday ishlaydi?

1. Anime videosini yuborasiz.
2. Gemini video va uning ichidagi audioni tahlil qiladi: personaj emotsiyasi, vaziyat, kerakli ovoz kuchi, ohang, tezlik, pauza va urg‘ular.
3. Video ichidagi nutq eshitilsa, uning sahna bilan mosligi haqida xulosa beradi. Nutq eshitilmasa, soxta baho bermaydi.
4. Alohida voice/audio yuborsangiz, bot uni shu video bilan solishtiradi.
5. Natijada emotsiya mosligi, ovoz ifodasi, tezlik, pauza, talaffuz va o‘lchash mumkin bo‘lsa sinxronlik bo‘yicha izoh hamda baho olasiz.

Bot baland ovozni avtomatik ravishda yaxshi ijro deb hisoblamaydi. U vaziyatga mos aktyorlikni baholashga yo‘naltirilgan.

## Texnologiyalar

- Python 3.10+
- aiogram 3
- Google Gen AI Python SDK
- Gemini multimodal Interactions API
- Har bir foydalanuvchi uchun lokal sessiya xotirasi

Hozirgi repo Telegram bot MVP uchun. Web platforma keyingi bosqichda shu AI xizmatlariga ulanadi.

## 1. Telegram bot tokeni

Telegram’da BotFather orqali bot yarating va token oling. Tokenni hech qachon GitHub’ga joylamang.

## 2. Gemini API kaliti

Google AI Studio orqali Gemini API key oling. Model va API uchun foydalanish limitlari hamda narxlar hisob va modelga qarab farq qilishi mumkin; ishlatishdan oldin AI Studio'dagi joriy limitlarni tekshiring.

## 3. Termux orqali ishga tushirish (Android)

Termux'ni ochib, buyruqlarni bittadan bajaring:

    pkg update && pkg upgrade -y
    pkg install python git ffmpeg -y
    git clone https://github.com/bekiuz/bekiuz-dublab.git
    cd bekiuz-dublab
    python -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt

.env faylini yarating:

    cp .env.example .env
    nano .env

Ichidagi qiymatlarni o‘zingiznikiga almashtiring:

    BOT_TOKEN=BotFather_tokeningiz
    GEMINI_API_KEY=Gemini_API_kalitingiz
    GEMINI_MODEL=gemini-3.8-flash
    DATA_DIR=data

Nano'da saqlash: CTRL + O, Enter, keyin CTRL + X.

Botni ishga tushirish:

    python bot.py

Termux’da ekran o‘chganda ish to‘xtab qolmasligi uchun Termux wake lock funksiyasidan foydalanish mumkin. Android batareya optimizatsiyasi baribir jarayonni to‘xtatishi mumkin; telefon doimiy hosting kabi kafolat bermaydi.

## Telegram Local Bot API Server (fayl hajmi cheklovini olib tashlash)

Local Bot API — Telegram'ning rasmiy ochiq kodli serveri. `--local` rejimida fayllarni yuklab olish hajmi cheklanmaydi, server orqali yuklash esa 2000 MB gacha bo‘ladi. Bu Telegram cloud API'dagi 20 MB yuklab olish limitidan farq qiladi.

### Kerak bo‘ladigan ma'lumotlar

- Telegram bot tokeni — BotFather'dan.
- `api_id` va `api_hash` — Telegram Developer portalidan, shaxsiy Telegram akkauntingiz bilan olinadi. Bu qiymatlarni hech kimga yubormang.
- Local Bot API server binari — `telegram-bot-api`.

### Local serverni ishga tushirish

Telegram'ning rasmiy build yo‘riqnomasi C++17 compiler, OpenSSL, zlib, gperf va CMake talab qiladi. Linux uchun rasmiy umumiy build buyruqlari:

    git clone --recursive https://github.com/tdlib/telegram-bot-api.git
    cd telegram-bot-api
    mkdir build
    cd build
    cmake -DCMAKE_BUILD_TYPE=Release ..
    cmake --build . --target install

Build tugagach, `telegram-bot-api` binari o‘rnatilgan bo‘ladi. Serverni o‘z API ma'lumotlaringiz bilan boshlang:

    telegram-bot-api --api-id=YOUR_API_ID --api-hash=YOUR_API_HASH --local --http-port=8081

Server ishlashda davom etishi kerak. Bot ham shu qurilmada va shu fayl tizimida ishlashi zarur: Local Bot API `getFile` javobida faylning serverdagi mutlaq yo‘lini qaytaradi.

### Botni Local API'ga ulash

`.env` faylida:

    TELEGRAM_API_BASE_URL=http://127.0.0.1:8081
    TELEGRAM_LOCAL_MODE=true

1. Avval yuqoridagi Local Bot API serverini ishga tushiring.
2. Boshqa Termux oynasida loyiha papkasiga kirib, virtual muhitni faollashtiring.
3. Quyidagini bajaring:

       python switch_to_local.py

4. Skript server portini tekshiradi va cloud Bot API'dan chiqishdan oldin `LOGOUT` tasdig‘ini so‘raydi. Faqat Local API tayyor bo‘lsa tasdiqlang.
5. Keyin botni ishga tushiring:

       python bot.py

Telegram cloud API'dan Local API'ga o‘tishdan oldin `logOut` chaqirilishi shart. Cloud API'ga qayta kirishda Telegram 10 daqiqa kutishni talab qiladi.

### Telefonda sinab ko‘rish: Termux + Ubuntu (tajriba)

PRoot-Distro orqali Termux ichida Ubuntu userland ochish mumkin. Bu rasmiy Telegram Android build'i emas; Ubuntu container ichida Linux build yo‘lini sinab ko‘ramiz. Telefon xotirasi/RAM yetarli bo‘lmasligi yoki build xatolashi mumkin.

Termux oynasida:

    pkg update && pkg upgrade -y
    pkg install proot-distro -y
    proot-distro install ubuntu:24.04
    proot-distro login ubuntu

Ubuntu ichida Telegram Local Bot API build dependencies va Python vositalarini o‘rnating:

    apt update
    apt install -y git cmake g++ clang gperf libssl-dev zlib1g-dev python3 python3-venv python3-pip

Keyin Telegram serverini build qiling:

    git clone --recursive https://github.com/tdlib/telegram-bot-api.git
    cd telegram-bot-api
    mkdir build
    cd build
    cmake -DCMAKE_BUILD_TYPE=Release ..
    cmake --build . --target install --parallel 1

Build tugasa, o‘zingizning api_id va api_hash qiymatlaringiz bilan serverni ishga tushiring:

    telegram-bot-api --api-id=YOUR_API_ID --api-hash=YOUR_API_HASH --local --http-port=8081

Server terminali ochiq tursin. Ikkinchi Termux oynasida yana Ubuntu'ga kiring (`proot-distro login ubuntu`), bot repository'sini o‘sha Ubuntu ichida klonlang va `TELEGRAM_API_BASE_URL=http://127.0.0.1:8081`, `TELEGRAM_LOCAL_MODE=true` qilib sozlang. So‘ng `python switch_to_local.py` va `python bot.py` ni bajaring.

Bot va Local Bot API serverni aynan bitta Ubuntu container/fayl tizimida ishlating: aks holda Local Bot API qaytargan mutlaq fayl yo‘lini bot topa olmaydi.

### Termux / Android haqida

Rasmiy Telegram build generatorida Windows, Linux, macOS va BSD oilalari bor; Android/Termux alohida build target sifatida ko‘rsatilmagan. Shuning uchun `telegram-bot-api` serverini Termux'da kompilyatsiya qilishni hozircha kafolatlab bo‘lmaydi. Python bot kodi esa Local API bilan ishlashga tayyor. Agar Termux'da server binarini build qilib bo‘lmasa, Local API va Python botni bir xil Linux qurilmada ishga tushirish kerak bo‘ladi — alohida qurilmalarda absolute file path mos kelmaydi.

> Muhim: Local Bot API Telegram yuklab olish limitini olib tashlaydi, ammo bu Gemini API, telefon xotirasi, internet tezligi yoki modelning media cheklovlarini olib tashlamaydi.

## 4. Windows / Linux orqali ishga tushirish

    python -m venv .venv

Windows PowerShell:

    .venv\Scripts\Activate.ps1

Linux/macOS:

    source .venv/bin/activate

Keyin:

    pip install -r requirements.txt
    cp .env.example .env

.env faylini tahrirlang va botni boshlang:

    python bot.py

## Telegram buyruqlari

- /start — boshlash
- /help — foydalanish tartibi
- /reset — oldingi video sessiyasini tozalash

## Fayl hajmi va maxfiylik

- Bot kodidagi avvalgi 18 MB ichki cheklov olib tashlandi.
- Telegram standart Bot API serveri getFile orqali botlarga 20 MB gacha faylni yuklab beradi. 20 MB dan kattaroq fayllar uchun Telegram'ning o‘z Local Bot API Server'ini alohida ishga tushirish kerak bo‘ladi.
- Sessiya videosi Termux ichidagi data/uploads/ papkasida saqlanadi.
- Sessiya ma'lumotlari data/sessions.json faylida turadi.
- data/ va .env GitHub’ga yuborilmaydi.
- Video va audio tahlil uchun Google Gemini API'ga uzatiladi. Tahlil tugagach, bot Gemini'ga vaqtincha yuklangan fayllarni o‘chirishga urinadi. Maxfiy yoki shaxsiy videolarni yubormang.
- /reset joriy sessiyadagi videoni o‘chiradi.

## Xatolar

- BOT_TOKEN yoki GEMINI_API_KEY xatosi: .env ni tekshiring.
- Fayl juda katta: Local API sozlanmagan bo‘lsa, Telegram cloud serverining 20 MB yuklab olish limiti amal qiladi. Local API sozlangan bo‘lsa server va bot bir qurilmada ishlayotganini tekshiring.
- Timed out: qisqaroq video yuboring yoki internetni tekshiring.
- API limit: AI Studio hisobingizdagi limit va model mavjudligini tekshiring.
- Bot javob bermasa: Termux'da python bot.py jarayoni ishlayotganini tekshiring.

## Reja

- [x] Video va audio Telegram handlerlari
- [x] Videoning ichki ovozini tahlil qilish
- [x] Alohida voice xabarni video bilan solishtirish
- [x] Lokal sessiya saqlash
- [ ] Real video va ovoz namunalari bilan sinov
- [ ] Web dashboard va baholash tarixi
