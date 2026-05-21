"""
Gemini AI Chatbot - Flask Backend
A premium AI chatbot powered by Google's Gemini API with conversation
history, multiple chat sessions, and streaming responses.
"""

import os
import json
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template, Response, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables from parent directory
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)


GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env file!")

client = genai.Client(api_key=GEMINI_API_KEY)

MODEL_NAME = "gemini-2.5-flash"

SYSTEM_INSTRUCTION = """You are Gemini Assistant, a helpful, knowledgeable, and friendly AI assistant.
You provide clear, accurate, and well-structured responses.
When writing code, always use proper syntax highlighting with markdown code blocks.
You can discuss any topic and help with coding, writing, analysis, math, and creative tasks.
Be concise but thorough. Use markdown formatting for better readability."""

conversations = {}


def get_or_create_conversation(conv_id=None):
    """Get existing conversation or create a new one."""
    if conv_id and conv_id in conversations:
        return conv_id, conversations[conv_id]

    new_id = str(uuid.uuid4())[:8]
    conversations[new_id] = {
        "id": new_id,
        "title": "New Chat",
        "created_at": datetime.now().isoformat(),
        "messages": [],
        "history": [],
    }
    return new_id, conversations[new_id]


# ─── Routes ─────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    """Serve the chatbot UI."""
    return render_template("chat.html")


@app.route("/api/conversations", methods=["GET"])
def list_conversations():
    """List all conversations."""
    conv_list = []
    for cid, conv in conversations.items():
        conv_list.append({
            "id": conv["id"],
            "title": conv["title"],
            "created_at": conv["created_at"],
            "message_count": len(conv["messages"]),
        })
    # Sort by creation time, newest first
    conv_list.sort(key=lambda x: x["created_at"], reverse=True)
    return jsonify(conv_list)


@app.route("/api/conversations", methods=["POST"])
def create_conversation():
    """Create a new conversation."""
    conv_id, conv = get_or_create_conversation()
    return jsonify({"id": conv["id"], "title": conv["title"]})


@app.route("/api/conversations/<conv_id>", methods=["GET"])
def get_conversation(conv_id):
    """Get a specific conversation with messages."""
    if conv_id not in conversations:
        return jsonify({"error": "Conversation not found"}), 404
    conv = conversations[conv_id]
    return jsonify({
        "id": conv["id"],
        "title": conv["title"],
        "created_at": conv["created_at"],
        "messages": conv["messages"],
    })


@app.route("/api/conversations/<conv_id>", methods=["DELETE"])
def delete_conversation(conv_id):
    """Delete a conversation."""
    if conv_id in conversations:
        del conversations[conv_id]
    return jsonify({"success": True})


@app.route("/api/conversations/<conv_id>/title", methods=["PUT"])
def update_title(conv_id):
    """Update conversation title."""
    if conv_id not in conversations:
        return jsonify({"error": "Conversation not found"}), 404
    data = request.json
    conversations[conv_id]["title"] = data.get("title", "New Chat")
    return jsonify({"success": True})


@app.route("/api/chat", methods=["POST"])
def chat():
    """Send a message and get a response from Gemini."""
    data = request.json
    user_message = data.get("message", "").strip()
    conv_id = data.get("conversation_id")

    if not user_message:
        return jsonify({"error": "Message is required"}), 400

    # Get or create conversation
    conv_id, conv = get_or_create_conversation(conv_id)

    # Auto-title from first message
    if not conv["messages"]:
        title = user_message[:50] + ("..." if len(user_message) > 50 else "")
        conv["title"] = title

    # Add user message
    conv["messages"].append({
        "role": "user",
        "content": user_message,
        "timestamp": datetime.now().isoformat(),
    })

    try:
        # Build contents from history
        contents = []
        for msg in conv["history"]:
            contents.append(types.Content(role=msg["role"], parts=[types.Part.from_text(text=msg["text"])]))
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_message)]))

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.7,
                max_output_tokens=8192,
            ),
        )
        ai_response = response.text

        # Update history
        conv["history"].append({"role": "user", "text": user_message})
        conv["history"].append({"role": "model", "text": ai_response})

        # Add AI response
        conv["messages"].append({
            "role": "assistant",
            "content": ai_response,
            "timestamp": datetime.now().isoformat(),
        })

        return jsonify({
            "conversation_id": conv_id,
            "title": conv["title"],
            "response": ai_response,
        })

    except Exception as e:
        error_msg = str(e)
        print(f"[Gemini Error] {error_msg}")
        return jsonify({"error": f"Gemini API error: {error_msg}"}), 500


@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    """Stream a response from Gemini using Server-Sent Events."""
    data = request.json
    user_message = data.get("message", "").strip()
    conv_id = data.get("conversation_id")

    if not user_message:
        return jsonify({"error": "Message is required"}), 400

    conv_id, conv = get_or_create_conversation(conv_id)

    if not conv["messages"]:
        title = user_message[:50] + ("..." if len(user_message) > 50 else "")
        conv["title"] = title

    conv["messages"].append({
        "role": "user",
        "content": user_message,
        "timestamp": datetime.now().isoformat(),
    })

    def generate():
        full_response = ""
        try:
            # Build contents from history
            contents = []
            for msg in conv["history"]:
                contents.append(types.Content(role=msg["role"], parts=[types.Part.from_text(text=msg["text"])]))
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_message)]))

            response = client.models.generate_content_stream(
                model=MODEL_NAME,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.7,
                    max_output_tokens=8192,
                ),
            )

            # Send conversation metadata first
            yield f"data: {json.dumps({'type': 'meta', 'conversation_id': conv_id, 'title': conv['title']})}\n\n"

            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk.text})}\n\n"

            # Update history
            conv["history"].append({"role": "user", "text": user_message})
            conv["history"].append({"role": "model", "text": full_response})

            # Save the full response
            conv["messages"].append({
                "role": "assistant",
                "content": full_response,
                "timestamp": datetime.now().isoformat(),
            })

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ─── Run Server ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*50)
    print("  Gemini AI Chatbot is running!")
    print("  Open: http://localhost:5050")
    print("=" * 50 + "\n")
    app.run(host="0.0.0.0", port=5050, debug=True)
