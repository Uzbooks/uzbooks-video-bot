# UzBooks — avtomatik video zavodi

Siz Telegram botga kitob yuborasiz. Tizim haftasiga 3 marta (dushanba, chorshanba, juma)
quyidagilarni o'zi bajaradi:

1. Kitobni o'qiydi va konspekt qiladi (Gemini, bepul).
2. 7 blitzdan iborat, taxminan 10 daqiqalik o'zbekcha ssenariy yozadi (Gemini, bepul).
3. Har bir bo'lim uchun rasm tayyorlaydi:
   - Google'da billing ulangan bo'lsa, rasmni Gemini (Nano Banana) yaratadi.
   - Billing bo'lmasa, tizim o'zi bepul dizayn-kartochka chizadi.
4. Ovoz yozadi:
   - Bepul variant: Microsoft Edge'ning o'zbekcha ovozi.
   - Agar kalitni qo'shsangiz: ElevenLabs.
5. Videoni yig'adi va sifat nazoratidan o'tkazadi.
6. Videoni YouTube'ga **yopiq (private)** holatda yuklaydi va sizga Telegram'da havola yuboradi.
   YouTube hali ulanmagan bo'lsa, videoni GitHub'dan yuklab olish havolasini yuboradi.

Siz videoni ko'rib chiqasiz va YouTube Studio'da **Publish / Schedule** tugmasini bosasiz.

---

## 💰 Pul sarflash shartmi?

**Yo'q, boshlash uchun pul kerak emas.**

| Qism | Bepul variant | Pullik variant (ixtiyoriy) |
|---|---|---|
| Kitob o'qish, ssenariy, sifat nazorati | **Gemini 2.5 Flash, bepul tarif** | — |
| Rasmlar | **Dizayn-kartochkalar** (avtomatik) | Gemini Nano Banana, rasm boshiga bir necha sent (billing kerak) |
| Ovoz | **Edge TTS** (`uz-UZ-SardorNeural`) | ElevenLabs Starter, oyiga taxminan 5 $ |
| Server | **GitHub Actions**, private repo uchun oyiga 2000 daqiqa bepul | — |
| YouTube'ga yuklash | **Bepul** | — |

Bilib qo'yish kerak bo'lgan jihatlar:
- **Gemini bepul tarifi:** daqiqasiga so'rovlar soni cheklangan. Tizim limitga tushsa o'zi kutib, qayta urinadi.
  Bepul tarifda Google yuborilgan matnlardan o'z mahsulotlarini yaxshilash uchun foydalanishi mumkin.
- **Edge TTS:** Microsoft'ning rasmiy pullik xizmati emas, bepul kutubxona. Ishlashiga kafolat yo'q.
  Kanalni monetizatsiya qilganingizda pullik ovozga (ElevenLabs) o'tish xavfsizroq.
- **ElevenLabs bepul tarifi:** oyiga taxminan 1 videoga yetadi. Tijoriy foydalanishga ruxsat yo'q va
  videoda ElevenLabs nomini ko'rsatish shart. Shuning uchun ElevenLabs kaliti qo'shilmasa,
  tizim avtomatik ravishda Edge ovozidan foydalanadi.

---

## O'rnatish

### 1-qadam. GitHub repozitoriy
1. https://github.com/new sahifasini oching.
2. Nomini `uzbooks` deb yozing va **Private** ni tanlang.
3. **Create repository** tugmasini bosing.
4. **uploading an existing file** havolasini bosing.
5. ZIP ichidagi `uzbooks` papkasidagi **barcha fayl va papkalarni** sudrab tashlang.
6. **Commit changes** tugmasini bosing.

⚠️ `.github` papkasi yashirin bo'lgani uchun yuklanmay qolishi mumkin. Yuklangandan keyin
repozitoriyda `.github/workflows/uzbooks.yml` fayli borligini tekshiring. Bo'lmasa:
1. **Add file → Create new file** ni bosing.
2. Nomiga `.github/workflows/uzbooks.yml` deb yozing.
3. ZIP ichidagi shu faylning matnini nusxalab qo'ying.

### 2-qadam. Telegram bot
1. Telegram'da **@BotFather** ni oching va `/newbot` deb yozing.
2. Botga nom va username bering. Username `bot` bilan tugashi kerak.
3. BotFather bergan **token**ni oling.
4. O'z botingizni oching va **Start** ni bosing.
5. **@userinfobot** ni ochib, /start ni bosing. U ko'rsatgan **Id** raqamini oling.

### 3-qadam. Gemini kaliti
https://aistudio.google.com/apikey sahifasida **Create API key** tugmasini bosing.

### 4-qadam. Kalitlarni GitHub'ga qo'yish
Repozitoriyda **Settings → Secrets and variables → Actions → New repository secret** ni bosing.
Har bir kalitni alohida qo'shing. Nomlarni harfma-harf aynan shunday yozing.

**Majburiy (3 ta):**

| Name | Qiymat |
|---|---|
| `GEMINI_API_KEY` | Gemini kaliti |
| `TELEGRAM_BOT_TOKEN` | BotFather bergan token |
| `TELEGRAM_ADMIN_ID` | @userinfobot ko'rsatgan raqam |

**Keyinroq qo'shiladi (ixtiyoriy):**

| Name | Nima uchun |
|---|---|
| `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` | YouTube'ga avtomatik yuklash (5-qadam) |
| `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` | ElevenLabs ovozi (pullik tarif tavsiya etiladi) |

⚠️ Kalitlarni hech qachon chatga, kodga yoki ochiq joyga yozmang. Ular faqat GitHub Secrets'da turishi kerak.

### 5-qadam. YouTube ruxsati (ixtiyoriy, keyinroq qilsa ham bo'ladi)
1. https://console.cloud.google.com ni oching va Gemini kalitingiz turgan loyihani tanlang.
2. **APIs & Services → Library** bo'limidan **YouTube Data API v3** ni topib, **Enable** ni bosing.
3. **OAuth consent screen** bo'limida:
   - User type: **External** ni tanlang.
   - Ilova nomiga `UzBooks` deb yozing va emailingizni kiriting.
   - ⚠️ **Publish app (In production)** ni bosing. Aks holda ruxsat 7 kundan keyin o'chib qoladi.
4. **Credentials → Create credentials → OAuth client ID → Desktop app** ni tanlang. JSON faylni yuklab oling
   va nomini `client_secret.json` ga o'zgartiring.
5. Kompyuteringizda `scripts` papkasida quyidagi buyruqlarni bajaring:
   ```
   pip install google-auth-oauthlib
   python get_youtube_token.py
   ```
   Brauzer ochiladi, kanal hisobingizni tanlang.
   "Google hasn't verified this app" chiqsa, **Advanced → Go to UzBooks** ni bosing.
6. Ekranda chiqqan 3 ta qiymatni GitHub Secrets'ga qo'ying.
7. Muqova avtomatik qo'yilishi uchun kanalni https://www.youtube.com/verify sahifasida telefon orqali tasdiqlang.

API orqali yuklangan videolar Google tekshiruvidan (audit) o'tmaguncha **yopiq** holatda qoladi.
Bu bizga mos, chunki siz baribir chiqarishdan oldin ko'rib chiqasiz.

### 6-qadam. Sinov
1. Botga bitta kitob faylini (PDF) yuboring.
2. GitHub'da **Actions** bo'limiga o'ting. **"I understand… enable"** tugmasi chiqsa, uni bosing.
3. **UzBooks → Run workflow** ni bosing, `task` maydoniga `collect` deb yozing va ishga tushiring.
   1–2 daqiqada bot **"✅ navbatga qo'shildi"** deb javob beradi.
4. Yana **Run workflow** ni bosing, bu safar `task` maydoniga `produce` deb yozing.
   20–40 daqiqada Telegram'ga muqova, hisobot va video havolasi keladi.

---

## Kundalik foydalanish

| Telegram'da | Nima qiladi |
|---|---|
| kitob faylini yuborish | navbatga qo'shadi (PDF, EPUB, TXT, DOCX, FB2, 20 MB gacha) |
| faylga izoh (caption) yozish | ssenariy uchun qo'shimcha ko'rsatma beradi |
| `/navbat` | navbatdagi kitoblarni ko'rsatadi |
| `/ochir 2` | 2-kitobni navbatdan olib tashlaydi |

Bot xabarlarga darhol emas, **soatiga bir marta** javob beradi.

**Jadval:** dushanba, chorshanba va juma kunlari 14:00 UTC (Germaniya vaqti bilan qishda 15:00, yozda 16:00).
Vaqtni o'zgartirish uchun `.github/workflows/uzbooks.yml` dagi `0 14 * * 1,3,5` ni tahrirlang.
U faylda ikki joyda turibdi, ikkalasini ham o'zgartiring.

## Sozlash (kodni o'zgartirmasdan)
**Settings → Secrets and variables → Actions → Variables** bo'limida quyidagilarni qo'shish mumkin:

| Variable | Qiymatlar | Standart |
|---|---|---|
| `TEXT_MODEL` | Gemini matn modeli | `gemini-2.5-flash` |
| `IMAGE_PROVIDER` | `auto` / `gemini` / `cards` | `auto` (Gemini, ishlamasa kartochka) |
| `TTS_PROVIDER` | `auto` / `edge` / `elevenlabs` | `auto` (ElevenLabs kaliti bo'lsa u, bo'lmasa Edge) |
| `EDGE_VOICE` | `uz-UZ-SardorNeural` (erkak) / `uz-UZ-MadinaNeural` (ayol) | `uz-UZ-SardorNeural` |
| `GEMINI_IMAGE_MODEL` | Nano Banana modeli | `gemini-2.5-flash-image` |

Matn uslubini quyidagi fayllarda o'zgartirasiz:
- `prompts/style.md` — ssenariy qoidalari
- `prompts/example_script.md` — namuna ssenariy
- `prompts/image_style.txt` — rasm uslubi

## Sifat nazorati nimani tekshiradi
- Bo'limlar to'liqligi, so'z soni, kirill harflari yo'qligi va sarlavha uzunligi.
- Gemini muharrir sifatida tekshiradi: faktlar kitobga mosmi, to'qilgan raqamlar yoki uzun iqtiboslar yo'qmi,
  imlo to'g'rimi. Baho 7/10 dan past bo'lsa, ssenariy 2 martagacha qayta yoziladi.
- Video davomiyligi (7,5–12,5 daqiqa), audio va rasmlar to'liqligi.

Jiddiy muammo topilsa, video YouTube'ga **yuklanmaydi** va sizga muammolar ro'yxati yuboriladi.
Barcha tayyor fayllar **Actions → ishga tushirish → Artifacts** bo'limida 7 kun saqlanadi.

## Muammolar
- **Bot javob bermayapti:** Actions yoqilganini va `collect` ishga tushganini tekshiring.
  Ishga tushirishni ochib, qizil ❌ chiqqan qadamni o'qing.
- **`429` / `RESOURCE_EXHAUSTED`:** Gemini bepul limitiga tushgan. Tizim o'zi kutadi, juda katta
  kitoblarda biroz uzoqroq ishlaydi.
- **`invalid_grant` (YouTube):** ruxsat eskirgan. 5-qadamdagi 5–6-bandlarni qayta bajaring.
- **"Kitobdan matn chiqmadi":** PDF skanerlangan (rasm ko'rinishida). Matnli versiyasini yuboring.
