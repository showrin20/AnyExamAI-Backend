"""
IELTS Speaking Router - Mounts Gradio speaking test UI as a FastAPI sub-app.

Accessible at /speaking
"""

import logging

import gradio as gr
from google.genai import types

from services.speaking_service import (
    CHAT_MODEL,
    SYSTEM_INSTRUCTION,
    _get_client,
    text_to_speech,
    transcribe,
)

logger = logging.getLogger(__name__)

# ── Gradio callback state (per-session via Gradio state) ──────────────


def start_test():
    """Start a new IELTS speaking test. Returns (history, audio, interactive flag, chat_state)."""
    client = _get_client()
    chat = client.chats.create(
        model=CHAT_MODEL,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
        ),
    )
    response = chat.send_message("START_TEST")
    audio_path = text_to_speech(client, response.text)
    # Gradio messages format: list of {"role": ..., "content": ...} dicts
    history = [{"role": "assistant", "content": response.text}]
    # Return chat object as Gradio State so each browser tab gets its own session
    return history, audio_path, gr.update(interactive=True), chat


def process_audio(audio_path, history, chat):
    """Transcribe user audio, get examiner response, and synthesize speech."""
    if audio_path is None or chat is None:
        gr.Warning("Please start a test first or record your answer.")
        return history, None, None, chat

    client = _get_client()

    # ASR
    user_text = transcribe(client, audio_path)
    if not user_text:
        gr.Warning("Could not understand the audio. Please try again.")
        return history, None, None, chat

    # LLM
    response = chat.send_message(user_text)
    ai_text = response.text

    # TTS
    audio_out = text_to_speech(client, ai_text)

    # Update history — Gradio messages format: list of {"role": ..., "content": ...} dicts
    history = history or []
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": ai_text})

    return history, audio_out, None, chat


# ── Build the Gradio Blocks app ──────────────────────────────────────

def create_speaking_app() -> gr.Blocks:
    """Build and return the Gradio Blocks app (without launching it)."""

    with gr.Blocks(title="IELTS Speaking Mock Test") as app:
        gr.Markdown(
            "# 🎙️ IELTS Speaking Mock Test\n"
            "Practice your IELTS speaking with an AI examiner. "
            "Click **Start New Test** to begin, then record your answers."
        )

        # Hidden Gradio State to hold the per-session chat object
        chat_state = gr.State(value=None)

        chatbot = gr.Chatbot(height=480, label="Conversation")
        audio_out = gr.Audio(label="Examiner Audio", autoplay=True, interactive=False)

        with gr.Row():
            start_btn = gr.Button("Start New Test", variant="primary", scale=1)
            audio_in = gr.Audio(
                sources=["microphone"],
                type="filepath",
                label="Record Your Answer",
                interactive=False,
                scale=2,
            )

        start_btn.click(
            fn=start_test,
            outputs=[chatbot, audio_out, audio_in, chat_state],
        )

        audio_in.stop_recording(
            fn=process_audio,
            inputs=[audio_in, chatbot, chat_state],
            outputs=[chatbot, audio_out, audio_in, chat_state],
        )

    return app
