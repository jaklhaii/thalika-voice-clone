# KM Voice Clone (@ckvoice_bot) — Setup & Usage Guide

## အနှစ်ချုပ်

KM Voice Clone bot သည် Telegram တွင် သုံးသူတစ်ဦးချင်းစီ၏ အသံ reference (voice sample) ကို သိမ်းဆည်းပြီး၊ ထိုအသံကိုပင် သုံး၍ စာသားမှ အသံ (TTS) ထုတ်ပေးသော bot ဖြစ်ပါသည်။ Code အားလုံး `bot.py` **တစ်ဖိုင်တည်း** တွင် ရေးထားပြီး pip install လုံးဝ မလိုပါ။

## Architecture

| အစိတ်အပိုင်း | နေရာ | ကုန်ကျစရိတ် |
|---|---|---|
| Telegram bot (`bot.py`) | GitHub Actions (free) | Free — ၂ မိနစ်တိုင်း အလိုအလျောက် run |
| Voice cloning server (VoxCPM2) | Google Colab (free GPU/CPU) | Free |
| Tunnel | Cloudflare Quick Tunnel | Free |

**GitHub repo:** [jaklhaii/thalika-voice-clone](https://github.com/jaklhaii/thalika-voice-clone)

## အဓိက Feature များ

- **ခလုတ်များ message အောက်မှာ** (ReplyKeyboardMarkup) — inline keyboard မဟုတ်
- **အားလုံး မြန်မာဘာသာ** — bot message နှင့် ခလုတ် label အားလုံး
- **Voice upload** — user က voice message ပို့လျှင် reference voice အဖြစ် သိမ်းပေး
- **Reference မရှိလျှင် အသံမထုတ်** — စာသားသီးသန့်ပို့လျှင် bot က အသံ မထုတ် (warning ပြ)
- **Per-user isolation** — သုံးသူတိုင်း၏ voice များ သီးခြားစီ သိမ်း (multi-user)
- **Owner self-service** — owner (8970380146) သာ Settings → Allow/Remove users ခလုတ်များ မြင်ရ
- **Progress bar** — `[█████░░░░░] 50%` format ဖြင့် generate အခြေအနေ ပြ
- **@Kmvclone contact button** — main menu တွင် ထည့်ထား
- **Job-mode generation** — Cloudflare timeout (60 စ) ကို ကျော်ဖြတ်ရာ job ID polling သုံးထား

## Colab Server ကို ပြန် run နည်း (Owner ကိုယ်တိုင် ပြုလုပ်ရန်)

Voice server သည် Colab free runtime တွင် run ထားရသည်။ Sandbox browser မှ runtime သည် memory ကန့်သတ်ချက်ကြောင့် ဆက်ကွပ်နေသောကြောင့် **သင့်ဖုန်း/ကွန်ပျူတာ browser မှ run ပေးရန် လိုအပ်ပါသည်** — တစ်ကြိမ် run လျှင် အောက်ပါအဆင့်များကို လုပ်ပေးရုံဖြစ်သည်။

1. Notebook ဖွင့်: https://colab.research.google.com/drive/1Jnk29QkHBAJI6pTi73AVohDVbUG4Z9vs
2. **Connect** ခလုတ်နှိပ် → GPU quota ကုန်နေလျှင် pop-up ပေါ်လာသည့်အခါ **"Connect without GPU"** နှိပ် (GPU ရရင် Runtime → Change runtime type → T4 GPU သုံးလျှင် အသံထုတ်ချိန် ပိုမြန်သည်)
3. Cell နှစ်ခုလုံးကို **Run** (cell ဘယ်ဘက် အောက်ပြောင်းခလုတ် သို့မဟုတ် Run all)
4. Cell 1 output ပြီးလျှင် `PUBLIC_URL=https://......trycloudflare.com` စာကြောင်း ပေါ်လာမည် — **ထို URL ကို ကူပြီး bot owner (@Kmvclone) ထံ ပို့ပေးပါ**
   - CPU mode ဖြစ်လျှင် cell 1 ပြီးရန် ~10-15 မိနစ် ကြာနိုင်သည် (pinned GPU ဆို ~5 မိနစ်)
5. bot owner က URL ကို `bot.py` မှာ update လုပ်ပြီး GitHub တွင် commit ချလိုက်ရုံဖြင့် bot က အသစ် server နှင့် အလုပ်လုပ်မည်

## Server URL ပြင်းနည်း (OWNER သာ ပြုလုပ်ရန်)

Colab Quick Tunnel သည် restart တိုင်း URL ပြောင်းပါသည်။ Owner အနေဖြင့်:

1. GitHub repo → `bot.py` → Edit (ပန်းခြစ် icon)
2. Line ~33: `SERVER_URL = "https://.....trycloudflare.com"` ကို အသစ် PUBLIC_URL ဖြင့် ပြင်
3. **Commit changes**
4. Actions tab → "KM Voice Clone Bot" → **Run workflow** (သို့မဟုတ် ၂ မိနစ်အတွင်း auto-run ဖြစ်မည်)
5. Telegram တွင် bot ကို /start နှိပ်ပြီး voice sample ပို့ခါ test လုပ်ပါ

## GitHub Actions

- Cron: `*/2 * * * *` (တစ်ခေါက် run လျှင် ~30 စက္ကန့်)
- Manual: Actions → KM Voice Clone Bot → Run workflow
- Free plan quota — workflow တစ်ခေါက် ~2 min; ၂၀၀၀ min/month free

## တစ်ခေါက် run ထားလျှင် ဘယ်နှစ်နာရီ သက်တမ်းရှိလဲ

- Colab free runtime သည် idle ~90 မိနစ်ကြာလျှင် အလိုအလျောက် ပိတ်သွားမည်
- Bot run mode: job-mode polling ဖြစ်သောကြောင့် အသံ generate တစ်ခေါက် လျှင် CPU ဖြစ် 2-8 မိနစ်၊ GPU ဖြစ် 15-40 စက္ကန့် ကြာပါမည်
- Runtime ပိတ်သွားလျှင် bot က "server မရသေးဘူး" ဟု အကြောင်းကြားပြ user ကို ထိခိုက်မှုမရှိစေပါ

## ဖိုင်များ

| ဖိုင် | တာဝန် |
|---|---|
| `bot.py` | Telegram bot (main, stdlib only, stdlib) — GitHub Actions တွင် run |
| `.github/workflows/bot.yml` | GitHub Actions auto-run workflow |
| `scripts/colab-server.py` | Colab voice server — notebook cell 1 ကို ထိုဖိုင်က GitHub မှ အလိုအလျောက် ဆွဲယူ run သည် |
