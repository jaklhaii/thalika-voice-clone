# KM Voice Clone — Setup Guide (Free Hosting + Colab GPU)

## စနစ် အလုပ်လုပ်ပုံ

```
[သင် Telegram မှာ ပို့]  →  [km-voice-bot.py — သင့် free hosting]
                                    ↓ (audio + text)
                          [Colab T4 GPU Server — FastAPI /generate]
                                    ↓ (VoxCPM2 voice clone)
                          [48kHz WAV ပြန်ပို့]  →  [Telegram အသံပြန်ပို့]
```

အလေးအနက် တွက်ချက်မှု (VoxCPM2) အားလုံး **Colab free GPU** မှာ ဖြစ်သွားတာကြောင့် free hosting က message ပြန်ပို့ရုံ lightweight အလုပ်ပဲ လုပ်ရတယ်။ စာတိုအတွက် **၁ မိနစ် အတွင်း**၊ စာရှည်အတွက် **၁-၂ မိနစ်** အတွင်း အသံရမယ်။ (တကယ်စမ်းသပ်မှုမှာ စာတို ၄၈ စက်ကန့်၊ စာရှည် ၆၉ စက်ကန့် ရခဲ့ပါတယ်။)

## အဆင့် ၁ — Colab Server ဖွင့်ရန်

1. ဒီ link ကို ဖွင့်ပါ: [thalika-voice-server.ipynb](https://colab.research.google.com/drive/1Jnk29QkHBAJI6pTi73AVohDVbUG4Z9vs)
2. Google account (`tiktokfaq0@gmail.com`) နဲ့ login ဝင်ပါ
3. **Runtime → Change runtime type → Hardware accelerator: T4 GPU** ရွေးပေးထားပါ
4. Notebook ထဲက **ပထမဆုံး cell** ကို နှိပ်ပြီး **▶ Run** နှိပ်ပါ — ဒီ cell က GitHub ကနေ server code အသစ်ကို download လုပ်ပြီး run ပေးပါတယ်
5. Cell output မှာ အောက်ပါတွေ မြင်ရပါမယ်:
   - `[km] model ready`
   - `[km] warmup ok`
   - `PUBLIC URL: https://xxxx-xxxx.trycloudflare.com` ← **ဒီ URL ကို copy ထားပါ**

> **အရေးကြီး:** Colab tab ကို **မပိတ်ပါနဲ့** — server က tab ဖွင့်ထားမှ run နေမယ်။ Session disconnect ဖြစ်ရင် cell ပြန် run ရုံပဲ (ဒါပေမဲ့ URL အသစ် ထပ်ရမယ် — အောက်ကြည့်ပါ)။

> **ပထမခါ run မှာ** model download + warmup ကြောင့် ၅-၁၀ မိနစ် ကြာနိုင်ပါတယ်။ Model cache ပြီးသားဆိုရင် နောက်ပိုင်း connect တိုင်း ၂-၃ မိနစ်လဲ သာ ကြာပါတယ်။

## အဆင့် ၂ — Bot File (km-voice-bot.py) ပြင်ဆင်ရန်

`km-voice-bot.py` ကို သင့် free hosting မှာ upload တင်ပါ။ ဖိုင်ထဲမှာ ပြင်ရမယ့် နေရာ ၃ ခု ရှိပါတယ်:

| နေရာ | ဘာထည့်ရမလဲ |
|------|-------------|
| `BOT_TOKEN` | Telegram @BotFather ကနေ ရတဲ့ token (ပေးထားပြီးသား — ဒါပေမဲ့ expose ဖြစ်ထားတဲ့ token ကို revoke လုပ်ပြီး အသစ်ယူပြီး ထည့်ပေးပါ) |
| `SERVER_URL` | Colab output က ရတဲ့ `https://xxxx.trycloudflare.com` URL |
| `OWNER_ID` | သင့် Telegram **numeric ID** — Telegram မှာ [@userinfobot](https://t.me/userinfobot) ကို `hi` ပို့ပါ၊ ID ပြန်ရမယ် |

> **OWNER_ID မထည့်ရင်** ဘယ်သူမှ bot သုံးလို့မရပါဘူး — owner က user ID တွေ add လုပ်ပေးမှ သုံးလို့ရပါမယ်။

## အဆင့် ၃ — Bot Start လုပ်ရန်

Bot file ကို သင့် hosting platform မှာ run ပါ။ ပြီးရင် Telegram မှာ bot ကို /start နှိပ်ကြည့်ပါ — main menu ခလုတ်တွေ ပြရင် အောင်မြင်ပါပြီ။

> **URL ပြောင်းသွားရင်:** Colab session restart တိုင်း Cloudflare URL အသစ်ရမယ်။ ပြောင်းသွားရင် `km-voice-bot.py` ထဲက `SERVER_URL` ကို URL အသစ်နဲ့ ပြင်ပေးပြီး bot ပြန် start ရုံပဲ။

## အသုံးပြုနည်း (Telegram)

1. **Voice message တစ်ခု ပို့ပါ** → "အသံကို သိမ်းဆည်းနှိုင်းဖို့ နာမတ်ပေးပါ" prompt ပြမယ် — နာမတ်တစ်ခု ရွေးပေးပါ
2. **`/voice မင္ဂလာပါ`** ပို့ပါ → သင့် reference အသံနဲ့သာ clone အသံထုတ်ပေးမယ်
3. စာတိုမှာ **အသံထုတ်နေတဲ့ progress bar** `████████░░ 80%` ပြမယ်
4. **@Kmvclone** ခလုတ်နဲ့ owner ကို ဆက်သွယ်နိုင်ပါတယ်
5. စာသားတစ်ခုတည်းပို့ရင် အသံ **မထုတ်ပေးပါဘူး** — reference voice ရှိမှသာ ထုတ်ပေးမယ်
6. သင့်အသံတွေက သင့် account မှာသာ သိမ်းထားပါတယ် — တစ်ခြား user တွေရဲ့ အသံနဲ့ ရောမသွားပါဘူး

## Owner Controls

| Command | အလုပ်လုပ်ပုံ |
|---------|---------------|
| `/add 123456789` | User ID ကို allow လုပ်ပေးမယ် (owner သာသုံးနိုင်) |
| `/remove 123456789` | User ID ကို ဖယ်ရှားမယ် |
| `/list` | Allow ဖြစ်နေတဲ့ users တွေ ကြည့်မယ် |

## ကန့်သတ်ချက် (Free Tier)

- Colab free GPU session ဟာ idle ဖြစ်ရင် disconnect ဖြစ်တယ် — ဖြစ်ရင် cell ပြန် run ပြီး URL အသစ် bot ထဲထည့်ရုံ
- Colab free GPU ရနိုင်မှုက နေ့စဉ် usage အလျှောက် ကန့်သတ်တယ် — ၂၄/၇ အာမခံမရ (တစ်ခါတည်းမှာ ၁ request သာ process လုပ်တယ်)
- ၂၄/၇ အာမခံလိုရင် GPU VM (RunPod ~$0.2/h) သုံးရမယ်

## Security မှတ်ချက်

- Bot token က chat ထဲမှာ expose ဖြစ်ထားခဲ့တယ် — **@BotFather မှာ /revoke နဲ့ token အသစ်ယူပြီး** `km-voice-bot.py` ထဲထည့်ပါ
- ဘယ်သူမှ bot ကို abuse မလုပ်နိုင်အောင် OWNER_ID + user whitelist ထားပြီးသားပါ
