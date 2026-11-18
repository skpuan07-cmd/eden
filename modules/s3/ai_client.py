"""
S3 AI Client - Python wrapper around z-ai-web-dev-sdk CLI

This module provides a unified interface for Sahana Eden controllers to call
AI capabilities (LLM chat, vision, TTS, ASR, function calling) via the z-ai CLI.

Usage:
    from s3.ai_client import AIClient
    client = AIClient()
    response = client.chat("Hello", system="You are a Sahana Eden assistant")
    description = client.describe_image("/path/to/image.jpg", prompt="What is in this image?")
    transcript = client.transcribe_audio("/path/to/audio.wav")
    audio_path = client.synthesize_speech("สวัสดีครับ", output_path="/tmp/hello.wav")
"""
import json
import os
import subprocess
import tempfile
import logging

logger = logging.getLogger(__name__)


class AIClientError(Exception):
    """Raised when an AI call fails."""
    pass


class AIClient:
    """Wrapper around the z-ai CLI for Sahana Eden."""

    def __init__(self, timeout=120):
        self.timeout = timeout
        self.cli_path = self._find_cli()

    @staticmethod
    def _find_cli():
        """Find the z-ai CLI binary."""
        for path in ["/usr/local/bin/z-ai", "/usr/bin/z-ai"]:
            if os.path.exists(path):
                return path
        # Try PATH
        import shutil
        cli = shutil.which("z-ai")
        if not cli:
            raise AIClientError(
                "z-ai CLI not found. Install z-ai-web-dev-sdk and ensure 'z-ai' is in PATH."
            )
        return cli

    def _run(self, args, return_json=True):
        """Run the z-ai CLI with given args, return parsed JSON.

        Uses UTF-8 encoding explicitly so Thai/CJK characters in prompts
        don't trigger 'ascii codec can't decode' errors.
        """
        import subprocess as sp
        # Pass args via env-safe mechanism; UTF-8 for stdin/stdout/stderr
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["LANG"] = "en_US.UTF-8"
        env["LC_ALL"] = "en_US.UTF-8"
        cmd = [self.cli_path] + args
        logger.debug("Running: %s", " ".join(cmd))
        try:
            result = sp.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                check=False,
                env=env,
            )
        except sp.TimeoutExpired:
            raise AIClientError(f"z-ai CLI timed out after {self.timeout}s")
        except Exception as e:
            raise AIClientError(f"Failed to invoke z-ai CLI: {e}")

        # The CLI prints "🚀 Initializing..." lines to stderr; JSON to stdout
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()

        if result.returncode != 0:
            raise AIClientError(
                f"z-ai CLI exit {result.returncode}: {stderr or stdout}"
            )
        if not stdout:
            raise AIClientError(f"z-ai CLI produced no output. stderr: {stderr}")

        if return_json:
            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                # The CLI sometimes prints diagnostic lines before the JSON.
                # Try to extract the JSON portion.
                start = stdout.find("{")
                if start >= 0:
                    try:
                        return json.loads(stdout[start:])
                    except json.JSONDecodeError:
                        pass
                raise AIClientError(f"Could not parse JSON output: {stdout[:500]}")
        return stdout

    # -----------------------------------------------------------------
    # Text LLM
    # -----------------------------------------------------------------
    def chat(self, prompt, system=None, thinking=False):
        """
        Chat completion.

        Args:
            prompt: User message text
            system: Optional system prompt
            thinking: Enable chain-of-thought reasoning (slower)

        Returns:
            dict with keys: content, model, usage, raw
        """
        args = ["chat", "--prompt", prompt]
        if system:
            args += ["--system", system]
        if thinking:
            args += ["--thinking"]
        data = self._run(args)
        choice = data.get("choices", [{}])[0]
        return {
            "content": choice.get("message", {}).get("content", ""),
            "model": data.get("model"),
            "usage": data.get("usage", {}),
            "raw": data,
        }

    def chat_messages(self, messages, thinking=False):
        """
        Multi-turn chat with a list of {role, content} dicts.
        Uses the CLI single-shot chat under the hood by serializing context
        into the prompt (since the CLI doesn't expose /v1/chat/completions
        directly with arbitrary message lists).
        """
        # Build a single prompt from the message history
        rendered = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                rendered.append(f"[System]\n{content}")
            elif role == "assistant":
                rendered.append(f"[Assistant]\n{content}")
            else:
                rendered.append(f"[User]\n{content}")
        prompt = "\n\n".join(rendered)
        # Pull the last system message out as a --system arg if present
        system = None
        for m in messages:
            if m.get("role") == "system":
                system = m.get("content")
        return self.chat(prompt, system=system, thinking=thinking)

    def chat_json(self, prompt, system=None):
        """
        Like chat() but parses the response content as JSON.
        Returns the parsed object, or raises AIClientError on parse failure.
        """
        result = self.chat(prompt, system=system)
        content = result["content"]
        # Strip markdown code fences if present
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines)
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise AIClientError(f"LLM response was not valid JSON: {e}\nContent: {content[:500]}")

    # -----------------------------------------------------------------
    # Vision
    # -----------------------------------------------------------------
    def describe_image(self, image_path_or_url, prompt="Describe this image.", thinking=False):
        """
        Vision chat: send one image + a prompt, return the model's description.

        Args:
            image_path_or_url: Local file path OR a public URL.
            prompt: What to ask about the image.
            thinking: Enable chain-of-thought.

        Returns:
            dict same shape as chat()
        """
        args = ["vision", "--prompt", prompt, "--image", image_path_or_url]
        if thinking:
            args += ["--thinking"]
        data = self._run(args)
        choice = data.get("choices", [{}])[0]
        return {
            "content": choice.get("message", {}).get("content", ""),
            "model": data.get("model"),
            "usage": data.get("usage", {}),
            "raw": data,
        }

    def describe_image_json(self, image_path_or_url, prompt):
        """Like describe_image but parses response as JSON."""
        result = self.describe_image(image_path_or_url, prompt=prompt)
        content = result["content"]
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines)
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise AIClientError(
                f"Vision response was not valid JSON: {e}\nContent: {content[:500]}"
            )

    # -----------------------------------------------------------------
    # Speech to Text (ASR)
    # -----------------------------------------------------------------
    def transcribe_audio(self, audio_path):
        """
        Transcribe an audio file (wav/mp3/etc.) to text.
        Returns dict: {text, raw}
        """
        args = ["asr", "--file", audio_path]
        data = self._run(args)
        # The ASR response shape varies; try common fields.
        text = data.get("text") or data.get("transcript") or ""
        if not text and "choices" in data:
            text = data["choices"][0].get("message", {}).get("content", "")
        return {"text": text, "raw": data}

    # -----------------------------------------------------------------
    # Text to Speech (TTS)
    # -----------------------------------------------------------------
    def synthesize_speech(self, text, output_path=None, voice="tongtong", speed=1.0, fmt="wav"):
        """
        Convert text to an audio file. Returns the path to the saved audio file.

        Args:
            text: Text to synthesize.
            output_path: Where to save the audio. If None, uses a tempfile.
            voice: Voice name (default: tongtong).
            speed: 0.5-2.0.
            fmt: wav/mp3/pcm.

        Returns:
            str path to the saved audio file.
        """
        if output_path is None:
            fd, output_path = tempfile.mkstemp(suffix=f".{fmt}", prefix="ai_tts_")
            os.close(fd)
        args = [
            "tts",
            "--input", text,
            "--output", output_path,
            "--voice", voice,
            "--speed", str(speed),
            "--format", fmt,
        ]
        # TTS writes the audio to output_path; we ignore stdout here.
        self._run(args, return_json=False)
        if not os.path.exists(output_path):
            raise AIClientError(f"TTS did not produce expected file: {output_path}")
        return output_path

    # -----------------------------------------------------------------
    # Function calling
    # -----------------------------------------------------------------
    def call_function(self, name, arguments):
        """
        Invoke a built-in function (e.g. web_search).

        Args:
            name: Function name (e.g. "web_search").
            arguments: dict of arguments.

        Returns:
            dict (parsed JSON result).
        """
        args_str = json.dumps(arguments, ensure_ascii=False)
        args = ["function", "--name", name, "--args", args_str]
        return self._run(args)
