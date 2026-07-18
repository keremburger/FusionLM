🧬 FusionLM — FAQ / Troubleshooting
🚧 This project is in alpha. Expect frequent bugs and incomplete/half-baked features.
If something breaks, please open an issue on GitHub — describing what you did, the
exact error message in the terminal, and your OS helps a lot. 🙏

🇹🇷 The app opens in Turkish / wrong language / my old chats show up
This means a fusionlm_config.json and/or fusionlm.db file from a previous run is sitting next to your source files. These are not the app itself, but user-specific state files — delete them (or move them elsewhere) and restart the app, it will be recreated in clean English. .gitignore already excludes both, so this shouldn't happen on a fresh clone — it only happens if you reuse a previously run folder. 🔄

🤷 The model list is empty
Make sure Ollama is installed and running (ollama serve) and that you have pulled at least one model:

Bash
ollama pull llama3.1
Then press the 🔄 button to refresh the list.

🎙️ How do I select the right microphone?
You can select your desired input device from the Microphone dropdown menu under Settings → Voice. If you plugged in a new microphone/headset, press the 🔄 button next to it to refresh the list. When "System Default" is selected, the app always uses your operating system's default input device.

🎤 The microphone says "No speech detected"
Before listening to your speech, the app listens to a short ~400 ms sample of silence to calibrate itself to the room's background noise, then waits for your voice to significantly exceed this threshold. If it still can't hear you:

Make sure the correct microphone is selected as the default input device in your OS sound settings — the app always uses the system default.

Speak within ~20 seconds after pressing the microphone button (this is the maximum recording time per turn).

In very noisy environments, the calibrated threshold might rise above normal speech — try it in a quieter place or speak a bit closer/louder into the microphone. 🔊

🗣️ TTS is reading my language with the wrong accent / is incomprehensible
By default, the spoken voice automatically adapts to the chat language you selected from the top bar (Settings → Voice → "Match voice to chat language automatically" should remain checked). If you pinned a manual voice ID and it doesn't match the chat language, either turn auto-matching back on or change the manual voice ID to the correct language (e.g., tr-TR-AhmetNeural for Turkish, en-US-GuyNeural for English).

If you are using the Kokoro engine: it currently doesn't support Turkish at all — switch the TTS Engine to EdgeTTS in Settings → Voice. 🇬🇧

🔁 Voice Chat stops responding after talking
Voice Chat is a loop: listen until you stop speaking → send what you said to the model → speak the response → listen again. A few checkpoints:

If you are using speakers (not headphones), the microphone might pick up the model's own audio response as if you were speaking, which can mess up the next listening turn. Headphones completely prevent this. 🎧

If nothing was transcribed (empty/very short audio), the app silently starts listening again and won't send an empty message — this is normal, try speaking again shortly after the microphone turns red.

Check that a model is selected and Ollama is running; if the model call itself fails, Voice Chat will show an error window instead of continuing to listen.

🌐 Web search gives a "connection error" / "DNS error"
This means the machine running FusionLM cannot reach the search backends (first DuckDuckGo, then automatically Google News RSS fallback). This is a local network/DNS issue, the app cannot fix it on its own — check:

If you have a working internet connection.

If there is a firewall/VPN/DNS filter blocking duckduckgo.com or news.google.com.

Corporate networks sometimes specifically block these — try a different network to verify.

If the model's response describes a very specific reason (like "DNS error while reaching Bing"), this is the model explaining a generic error message in its own words, not a real system log — the summary is always the same: the app couldn't reach the internet for that request. 🚫

🌍 Can I use a language other than English/Turkish?
Yes — see the "Adding a language" section in the README. It only comes with English and Turkish by default to keep the UI translation set small and complete.

💾 Where is my data stored?
Everything is local: fusionlm_config.json (settings) and fusionlm.db (chats, SQLite) sit next to your source files. Aside from LLM calls, nothing is sent anywhere; requests only go out to services like TTS/web-search (if you enable them), and those go directly from your machine to those services. 🔒

🧯 The app crashed, how do I reset it?
Close the app, delete the fusionlm_config.json and fusionlm.db files, and restart.