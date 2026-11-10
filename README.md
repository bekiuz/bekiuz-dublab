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
    MAX_MEDIA_MB=18

Nano'da saqlash: CTRL + O, Enter, keyin CTRL + X.

Botni ishga tushirish:

    python bot.py

Termux’da ekran o‘chganda ish to‘xtab qolmasligi uchun Termux wake lock funksiyasidan foydalanish mumkin. Android batareya optimizatsiyasi baribir jarayonni to‘xtatishi mumkin; telefon doimiy hosting kabi kafolat bermaydi.

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

## Fayl limitlari va maxfiylik

- Telegram Bot API standart getFile orqali yuklab olish limiti 20 MB. Bot standart holatda 18 MB limit qo‘yadi.
- Sessiya videosi Termux ichidagi data/uploads/ papkasida saqlanadi.
- Sessiya ma'lumotlari data/sessions.json faylida turadi.
- data/ va .env GitHub’ga yuborilmaydi.
- Video va audio tahlil uchun Google Gemini API'ga uzatiladi. Tahlil tugagach, bot Gemini'ga vaqtincha yuklangan fayllarni o‘chirishga urinadi. Maxfiy yoki shaxsiy videolarni yubormang.
- /reset joriy sessiyadagi videoni o‘chiradi.

## Xatolar

- BOT_TOKEN yoki GEMINI_API_KEY xatosi: .env ni tekshiring.
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
