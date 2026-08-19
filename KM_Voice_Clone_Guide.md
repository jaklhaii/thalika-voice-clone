# KM Voice Clone (@ckvoice_bot) — Setup & Usage Guide (Colab ဗားရှင်း)

KM Voice Clone bot သည် Telegram တွင် သုံးသူတိုင်း၏ အသံ reference (voice sample) ကို သီးသန့်သိမ္းဆည်းပြီး ထိုအသံကိုပင် သုံးကာ စာသားမှ အသံ (voice clone) ထုတ်ပေးသော bot ဖြစ်သည်။ Bot နှင့် အသံထုတ် machine learning model (VoxCPM2) အားလုံး **Google Colab** တစ်နေရာတည်းတွင် run ပါသည် — Colab ၏ အခမဲ့ GPU ဖြင့် high-quality 48 kHz WAV ထုတ်ပေးသည်။

## Bot run နည်း (Owner လုပ်ရမည့်အစ ပြင်ဆင်မှု)

`km_voice_clone_colab.ipynb` ကို Google Colab မှာ ဖွင့်ပါ ([colab.research.google.com](https://colab.research.google.com/) → File → Open notebook → Upload)။ Notebook တွင် **cell ၃ ခု** ရှိပြီး အောက်မှအထက် အစီအစဉ်လိုက် run ပါ။

| Cell | တာဝန် | အချိန် |
|---|---|---|
| 1 | `voxcpm` library တပ်ဆင် + VoxCPM2 model (~9 GB) download | ပထမအကြိမ် ၅–၁၅ မိနစ် (ကြားတွင် **Connect** ကို နှိပ်ပါ၊ GPU ရရင် ပိုမြန်သည်) |
| 2 | `bot.py` (bot ပရိုဂရမ်) ကို load ပါသည် | စက္ကန့်အနည်းငယ် |
| 3 | Bot ကို စတင်ရန် (`run()`) — **ဒီ cell မပိတ်ပါနဲ့** | ချက်ချင်း |

Cell 3 output တွင် `KM Voice Clone — starting... is listening` ပေါ်ရင် bot အသင့်ဖြစ်ပြီ။ **Colab tab ကို browser မှာ ဆက်ဖွင့်ထားပါ** — ပိတ်လိုက်ရင် bot ရပ်ပါမည်။ ရပ်သွားရင် cell 3 ကို ပြန် run ရုံဖြင့် ပြန်စနိုင်သည်။ Colab free plan တွင် ~၉၀ မိနစ် idle ဖြစ်လျှင် session ရပ်နိုင်သည်။

## အသုံးပြုနည်း (Telegram မှာ)

ခလုတ်အားလုံးက Telegram message **အောက်မှာ တွဲပါတဲ့ inline ခလုတ်များ** ဖြစ်ပြီး နှိပ်ရုံနဲ့ ချက်ချင်း တုန့်ပြန်ပါသည်။

| အဆင့် | လုပ်ရမည့်အရာ |
|---|---|
| ၁ | Bot ကို **/start** ပို့ပါ — မူလမီနူး ၂×၂ ခလုတ်များ ပေါ်လာမည် |
| ၂ | **🎤 ကျွန်တော့အသံများ** → **➕ အသံထည့်မည်** နှိပ်ပြီး အသံအမည် ရေးပို့ပါ |
| ၃ | **အသံ message (သို့) audio ဖိုင်** ပို့ပေးပါ — reference အဖြစ် သိမ်းမည် |
| ၄ | **🔊 အသံထုတ်မည်** နှိပ် → မိမိအသံကို ရွေးပါ → **စာသားကို ပို့ပါ** |
| ၅ | Progress bar `[▓▓▓░░] 40%` ပြပြီး စက္ကန့်အနည်းငယ် (စာသားအလိုက် ၁–၅ မိနစ်) 48 kHz WAV ပြန်ရမည် |

**သတိ** — စာသားသီးသန့်ပို့ရင် အသံ မထုတ်ပါ။ Reference အသံရှိမှသာ ထုတ်ပေးသည်။ Reference သည် ကိုယ့်အသံသာ သုံးသည် — **အခြားသူ့အသံများနဲ့ ရောစပါမည်**။

## Owner ထိန်းချုပ်မှု

**⚙️ ဆောင်ရွက်ချက်များ** ခလုတ်က owner သာ မြင်ရပြီး — **➕ အသုံးပြုသူထည့်မည်** / **➖ အသုံးပြုသူဖယ်မည်** / **📋 အသုံးပြုသူစာရင်း** / **🖥 Server အခြေအနေ** — ဖြင့် ခွင့်ပြုစာရင်းကို စီမံခန့်ခွဲနိုင်သည်။ Owner ထည့်ထားမှသာ သုံးသူအသစ်များ bot ကို သုံးနိုင်သည်။ ဆက်သွယ်ချင်ရင် **ဆက်သွယ်ရန် @Kmvclone** ခလုတ်ကို သုံးပါ။

## ဖိုင်များ

| ဖိုင် | တာဝန် |
|---|---|
| `bot.py` | Telegram bot အလုံးစုံ (stdlib only — Colab မှာ ချက်ချင်း run နိုင်သည်) |
| `km_voice_clone_colab.ipynb` | Colab notebook (cell 1 install/model, cell 2 bot, cell 3 run) |
| `test_logic.py` | Logic test — `python3 test_logic.py` ဖြင့် 27/27 စစ်နိုင်သည် |

## ပြင်ဆင်လိုပါက

Owner အနေဖြင့် GitHub repo [`jaklhaii/thalika-voice-clone`](https://github.com/jaklhaii/thalika-voice-clone) ထဲက `bot.py` ကို online edit လုပ် commit ချပြီး notebook ကို Colab မှာ **Runtime → Restart and run all** ဖြင့် ပြန် run ရုံဖြင့် အသစ် update ဖြစ်သည်။ `OWNER_ID` နှင့် `TG_BOT_TOKEN` ကို `bot.py` ထိပ်တွင် သတ်မှတ်ထားသည်။
