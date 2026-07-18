# 🧬 FusionLM – Local Multi-Model AI Chat

**FusionLM** is a powerful, modern desktop client that **fuses** multiple local LLM models, personas, media tools, and web search into one seamless interface. Built on top of Ollama, it offers everything a privacy‑focused power user could dream of.

> "Why settle for one model when you can fuse them all?"

---

## 🚧 Alpha software — expect bugs!

FusionLM is currently in **early alpha**. It works, but crashes, half-finished
features, and rough edges are expected — this is not a polished, stable
release yet. 🐛

**If something breaks, please tell me!** Open an issue on GitHub with:
- what you did right before it broke,
- the full error/traceback from the terminal (if any),
- your OS and Python version.

Every bug report genuinely helps make this better. Thanks for testing it out! 🙏

---

## 🙏 Credits

Some pieces of this project (🎬 **actions**, 🔊 **TTS**, 🎤 **STT**) were forked and adapted from **Fatih Makes'** project **[Mark-XLIX](https://github.com/FatihMakes/Mark-XLIX)**. Huge thanks for the original work! 💛

---

## ✨ Features

### 🔀 Model Fusion
- **Multi‑model chat** – Choose any Ollama model from the dropdown or type a name manually
- **Compare mode** – Enable ⇆ to get side‑by‑side answers from two different models
- **4 AI modes** – Lite (fast ⚡), Normal (balanced ⚖️), Pro (expert 🧠), Coding (software focused 💻)
- **Customizable prompts** – Edit system prompts for each mode in Settings

### 🧠 Smart Context
- **Personas** – Predefined roles (Accountant, Programmer, Teacher, Doctor, Lawyer, Psychologist, Writer) plus custom persona editor
- **User profile** – Tell the AI about yourself, it remembers across conversations
- **20 languages** – AI responds in your chosen language, enforced via system prompt

### 🌐 Web & Media
- **Web search** – Toggle 🌐 to auto‑enrich queries with DuckDuckGo results
- **Screenshot analysis** – 📷 captures your screen, AI answers questions about it
- **Webcam input** – 📹 snaps a photo, asks AI instantly
- **File uploads** – Images (multimodal models), videos (first frame), audio (transcription), text/code files
- **Voice input** – 🎤 with optional "Hey Fusion" wake word

### 🗣️ Speech
- **Text‑to‑Speech** – 🔊 reads AI replies aloud in 20+ languages
- **Microphone selection** – Settings → Voice → Microphone lets you pick which input
  device to record from, with a 🔄 refresh button if you just plugged something in
- **Instant interrupt** – press **Esc** anytime to immediately stop FusionLM from
  speaking and/or listening (works mid-sentence, great for Voice Chat)
- **Multilingual UI** – 20 interface languages, switch anytime
- **Sync UI/AI language** – Option to keep interface in sync with AI language

### 🎨 Customization
- **12 themes** – Dark, Light, Dracula, Nord, Solarized Dark/Light, Monokai, One Dark, Tokyo Night, Catppuccin Mocha, Gruvbox Dark, Backrooms 🎨
- **Custom CSS** – Write your own styles in Settings for complete visual control
- **Opacity slider** – Make the window transparent (30‑100%) 🫥
- **Adjustable** – Font family/size, bubble radius, shadow blur/offset
- **Mini mode** – Hide sidebar for compact view

### 📊 System Monitor
- **Live stats** – CPU, RAM, GPU usage in bottom bar
- **Usage counter** – Fusions (messages) and tokens generated today

### 💾 Privacy
- **100% local** – All data stays in `fusionlm.db` and `fusionlm_config.json` 🔒
- **Export** – Save any conversation as `.txt`
- **Delete** – Right‑click to remove conversations

---

## 📦 Installation

### ✅ Prerequisites
- Python 3.10+
- [Ollama](https://ollama.com) installed and running
- At least one model pulled:
  ```bash
  ollama pull llama3.2
  ```

### 🛠️ Setup

```bash
git clone https://github.com/keremburger/FusionLM.git
cd FusionLM
pip install -r requirements.txt
python main.py
```

On first launch, `fusionlm_config.json` (settings) and `fusionlm.db` (chat history) are created next to the source files. Both are already excluded in `.gitignore`, so a fresh clone always starts clean. 🌱

---

## ⚙️ Settings

Open the ⚙ button to configure:

| Tab | What it controls |
|---|---|
| Generation | temperature, max tokens, top‑p/top‑k, context length, seed, stop sequences |
| Appearance | theme, font, bubble style, UI language, window opacity, custom CSS |
| Prompts | the system prompt used for each mode (Lite / Normal / Pro / Coding / Deep Research / Code Hub) |
| Voice | TTS engine, voice matching, Whisper model size, **microphone selection**, STT language, wake word, enable/disable actions |
| Persona | a custom persona appended to every system prompt |
| User | facts about you the model should keep in mind |

---

## 🤖 How actions work

When a request clearly matches a supported action (opening an app, searching the web, setting a reminder, etc.), the model's entire reply is a single JSON object instead of normal text; the app runs the action locally, feeds the result back to the model, and the model tells you the outcome in natural language. You never see the raw JSON. This feature is forked from [Mark-XLIX](https://github.com/FatihMakes/Mark-XLIX) and can be turned off in Settings → Voice → "Enable actions." 🎬

---

## 🌍 Adding a language

1. Add the language name to `LANGS` and its code to `LANG_CODES` in `translations.py`.
2. Add a matching entry to each string in the `TRANS` dict (or leave it — untranslated strings fall back to English).
3. (Optional) add a matching TTS voice mapping so Voice Chat speaks that language correctly.

---

## 🆘 Troubleshooting

See [FAQ.md](FAQ.md) for common issues (microphone not detected 🎤, TTS mispronouncing text 🔊, web search/news failing 🌐, models not showing up 🤷, etc.).

---

## 📜 License

**Personal and non-commercial use only.**
Licensed under [Creative Commons BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).

Parts of this project (actions, TTS, STT) are forked from **Fatih Makes' [Mark-XLIX](https://github.com/FatihMakes/Mark-XLIX)**, used here under the same non-commercial spirit — full credit to the original author. 🙌
