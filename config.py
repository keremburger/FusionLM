import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fusionlm_config.json")

DEFAULT_PROMPTS = {
    "Lite": "You are a fast, ultra-concise assistant. Give the shortest answer possible. No filler words.",
    "Normal": "You are a helpful, balanced assistant. Clear, structured answers. Friendly tone.",
    "Pro": "You are a world-class expert. Think step-by-step. Provide detailed analysis with examples.",
    "Coding": "You are an expert software engineer. Write clean, well-commented code. Explain briefly.",
    "Deep Research": (
        "You are an elite research analyst with access to vast knowledge. Approach every query systematically:\n"
        "1. **Executive Summary**: Frame the core question.\n"
        "2. **Background & Context**: Provide historical and contextual background.\n"
        "3. **Current State of Knowledge**: Summarize latest findings, trends, and expert consensus.\n"
        "4. **Divergent Perspectives**: Discuss different schools of thought, controversies, or open debates.\n"
        "5. **Evidence & Data**: Cite relevant statistics, studies, or real-world examples.\n"
        "6. **Limitations & Gaps**: Acknowledge what is still unknown or uncertain.\n"
        "7. **Future Outlook**: Predict possible developments or emerging trends.\n"
        "8. **Actionable Insights**: Offer practical recommendations or conclusions.\n"
        "Maintain a rigorous, neutral, academic tone. Always distinguish between fact and interpretation. "
        "When possible, reference sources by name (journal, author, year). "
        "Do not oversimplify; depth is more important than brevity."
    ),
    "Code Hub": (
        "You are a master software architect and educator. Your mission is to provide **production-ready**, "
        "elegant, and educational code.\n"
        "**Rules:**\n"
        "- Always output code in clean Markdown blocks with syntax highlighting.\n"
        "- Include a brief explanation of the architecture, algorithm, and design patterns used.\n"
        "- Mention time/space complexity (Big O) where applicable.\n"
        "- Highlight potential edge cases and how your code handles them.\n"
        "- Suggest tests (unit/integration) if appropriate.\n"
        "- Use modern language features and best practices.\n"
        "- If the user provides existing code, refactor it politely and explain the improvements."
    )
}

# Ses (STT/TTS) ve aksiyon ile ilgili yeni ayarlar — eski config dosyalarına
# da otomatik eklenir (load_cfg aşağıda setdefault ile tamamlar).
NEW_DEFAULTS = {
    "tts_engine": "edgetts",        # "edgetts" | "kokoro" | "elevenlabs"
    "tts_voice": "en-US-GuyNeural",
    "tts_auto_voice": True,          # auto-pick voice to match chat "language"
    "tts_speed": 1.0,
    "elevenlabs_api_key": "",
    "whisper_model": "base",
    "mic_device": "",                # "" = system default input device
    "stt_language": "auto",
    "actions_enabled": True,
    "voice_chat_enabled": False,
}


def load_cfg():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        prompts = cfg.get("custom_prompts", {})
        for k, v in DEFAULT_PROMPTS.items():
            prompts.setdefault(k, v)
        cfg["custom_prompts"] = prompts
        for k, v in NEW_DEFAULTS.items():
            cfg.setdefault(k, v)
        return cfg
    return {
        "theme": "Dark",
        "temperature": 0.7,
        "max_tokens": 800,
        "top_p": 0.9,
        "repeat_penalty": 1.1,
        "context_length": 4096,
        "language": "English",
        "ui_language": "English",
        "font_size": 10,
        "font_family": "Segoe UI",
        "top_k": 40,
        "seed": -1,
        "stop": "",
        "bubble_radius": 14,
        "shadow_blur": 8,
        "shadow_offset": 2,
        "sync_ui_lang": True,
        "tts_enabled": False,
        "tts_rate": 175,
        "tts_volume": 1.0,
        "custom_prompts": DEFAULT_PROMPTS.copy(),
        "custom_persona": "",
        "user_profile": "",
        "wake_word": "Hey Fusion",
        "wake_enabled": False,
        "compare_enabled": False,
        "web_search": False,
        "opacity": 100,
        "custom_css": "",
        "stats": {"tokens": 0, "messages": 0},
        **NEW_DEFAULTS,
    }

def save_cfg(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)