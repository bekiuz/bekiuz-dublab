# Bekiuz DubLab 🎙️

AI yordamida anime dublyaj sahnasi va ovoz aktyorligini baholovchi Telegram bot.

## Bot qanday ishlaydi?

1. Anime videosini yuborasiz.
2. Gemini video va uning ichidagi audioni tahlil qiladi: personaj emotsiyasi, vaziyat, kerakli ovoz kuchi, ohang, tezlik, pauza va urg‘ular.
3. Alohida voice/audio yuborsangiz, bot uni shu video bilan solishtiradi.
4. Natijada emotsiya mosligi, ovoz ifodasi, tezlik, pauza, talaffuz va o‘lchash mumkin bo‘lsa sinxronlik bo‘yicha izoh hamda baho olasiz.

Bot baland ovozni avtomatik ravishda yaxshi ijro deb hisoblamaydi. U vaziyatga mos aktyorlikni baholashga yo‘naltirilgan.

## Katta videolarni yuklash

Oddiy Telegram Bot API orqali getFile yuklab olish chegarasi 20 MB. Bekiuz DubLab katta fayllarni olish uchun Telethon + MTProto dan foydalanadi:

- aiogram bot xabarlarni odatdagidek qabul qiladi.
- Telethon aynan shu bot tokeni bilan MTProto orqali ulanadi.
- Bot API file_id Telethon orqali yechilib, fayl bo‘laklab bevosita Telegram serveridan olinadi.
- Shaxsiy Telegram akkaunti bilan telefon raqami orqali login qilish shart emas; MTProto ulanishi bot tokeni orqali amalga oshadi.

Bu yo‘lda Bot API HTTP getFile ning 20 MB cheklovi ishlatilmaydi. Biroq bu mutlaq cheksizlik va’da qilmaydi: Telegram tarafidagi cheklovlar, tarmoq, hosting diski, Gemini API/model limitlari va xarajatlari baribir amal qiladi.

## Kerakli kalitlar

1. BOT_TOKEN — Telegram'da @BotFather orqali olinadi.
2. GEMINI_API_KEY — Google AI Studio orqali olinadi.
3. TELEGRAM_API_ID va TELEGRAM_API_HASH — https://my.telegram.org sahifasidagi API Development Tools bo‘limidan olinadi. Bu qiymatlarni ommaga tarqatmang.

Telegram API ID va Hash — ilova uchun API kalitlari. Botning MTProto sessiyasi BOT_TOKEN bilan yaratiladi; botga tegishli sessiya fayli DATA_DIR ichida saqlanadi.

## Lokal ishga tushirish

Python 3.10+ tavsiya etiladi.

Linux / Termux:

    pkg update && pkg upgrade -y
    pkg install python git ffmpeg -y
    git clone https://github.com/bekiuz/bekiuz-dublab.git
    cd bekiuz-dublab
    python -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    cp .env.example .env

.env ichidagi BOT_TOKEN, GEMINI_API_KEY, TELEGRAM_API_ID va TELEGRAM_API_HASH qiymatlarini o‘zingiznikiga almashtiring. Kalitlarni hech qachon GitHub'ga yuklamang.

Botni ishga tushirish:

    python bot.py

Windows PowerShell'da virtual muhitni faollashtirish:

    .venv\Scripts\Activate.ps1

Keyin:

    pip install -r requirements.txt
    copy .env.example .env
    python bot.py

## Docker / cloud hosting

Repo ichida yengil Python Dockerfile bor. Telegram Local Bot API serverini build qilish shart emas.

Hosting sozlamalari:

- Build type: Dockerfile.
- Public port: kerak emas; bot Telegram bilan o‘zi ulanadi.
- Persistent volume: /data ga mount qiling.
- Replicas: 1 ta polling worker.
- Restart policy: on failure yoki always.

Secret/environment qiymatlari:

    BOT_TOKEN                 BotFather tokeni
    GEMINI_API_KEY            Gemini API kaliti
    GEMINI_MODEL              gemini-3.8-flash
    TELEGRAM_API_ID           Telegram API ID
    TELEGRAM_API_HASH         Telegram API Hash
    TELEGRAM_LOCAL_MODE       false
    DATA_DIR                  /data

Hostingdagi persistent volume'ni o‘chirmang: unda foydalanuvchi sessiyalari, vaqtinchalik media va Telethon bot sessiyasi saqlanadi. Bitta bot token bilan bir vaqtda faqat bitta polling instance ishlating.

Hostingning bepul tarifi, resurs limiti va uyqu siyosati provayderga bog‘liq. Docker image doimiy ishlashni o‘zi kafolatlamaydi.

## Telegram Local Bot API — muqobil usul

Agar keyinroq Local Bot API server ishlatmoqchi bo‘lsangiz, Telegram'ning rasmiy serveri hamon muqobil variant. --local rejimi yuklab olish hajmi cheklovini olib tashlaydi va server orqali yuklashni 2000 MB gacha ko‘taradi. U alohida telegram-bot-api serverini talab qiladi; bot va server bir xil fayl tizimiga ega bo‘lishi kerak.

MTProto yuklab olish yoqilgan bo‘lsa, odatda Local Bot API server shart emas.

## Telegram buyruqlari

- /start — boshlash
- /help — foydalanish tartibi
- /reset — oldingi video sessiyasini tozalash

## Fayl va maxfiylik

- Video va audio tahlil uchun Google Gemini API'ga yuboriladi.
- Sessiya videosi DATA_DIR/uploads/ papkasida saqlanadi.
- Sessiya ma'lumotlari DATA_DIR/sessions.json faylida saqlanadi.
- Telethon bot sessiyasi DATA_DIR/dublab-mtproto-bot.session faylida saqlanadi. Bu fayl maxfiy hisoblanadi.
- data/, .env va *.session* fayllarini GitHub'ga yuklamang yoki boshqalarga yubormang.
- Tahlil tugagach, bot Gemini'ga vaqtincha yuklangan fayllarni o‘chirishga urinadi.
- /reset joriy foydalanuvchining video sessiyasini tozalaydi.

## Xatolar

- BOT_TOKEN yoki GEMINI_API_KEY xatosi: .env ni tekshiring.
- TELEGRAM_API_ID/HASH xatosi: ikkalasi ham to‘g‘ri kiritilganini tekshiring.
- file_id MTProto formatiga aylantirilmadi: faylni Telegram'dan qayta yuborib ko‘ring.
- FloodWait: Telegram vaqtincha kutishni talab qilishi mumkin; kutish tugagach qayta urinib ko‘ring.
- Gemini xatosi: AI Studio'dagi model mavjudligi va foydalanish limitini tekshiring.

## Reja

- [x] Video va audio Telegram handlerlari
- [x] Videoning ichki ovozini tahlil qilish
- [x] Alohida voice xabarni video bilan solishtirish
- [x] Lokal sessiya saqlash
- [x] MTProto orqali katta media yuklash integratsiyasi
- [ ] Real Telegram bot bilan 20 MB dan katta faylda sinov
- [ ] Web dashboard va baholash tarixi
