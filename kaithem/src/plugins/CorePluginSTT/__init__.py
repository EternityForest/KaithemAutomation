from __future__ import annotations

import os
import subprocess
import threading
import time

from kaithem.api.tags import ObjectTag
from kaithem.src import alerts

model_sources: list[dict[str, float | int | str]] = [
    {"name": "sherpa-onnx-streaming-zipformer-en-2023-06-26", "size": 296},
    {
        "name": "sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23-mobile",
        "size": 51.8,
    },
    {
        "name": "sherpa-onnx-streaming-zipformer-en-20M-2023-02-17-mobile",
        "size": 103,
    },
    {
        "name": "sherpa-onnx-streaming-zipformer-en-2023-06-26-mobile",
        "size": 291,
    },
    {
        "name": "sherpa-onnx-streaming-zipformer-multi-zh-hans-2023-12-12-mobile",
        "size": 288,
    },
    {
        "name": "sherpa-onnx-streaming-zipformer-korean-2024-06-16-mobile",
        "size": 360,
    },
    {
        "name": "sherpa-onnx-streaming-zipformer-fr-2023-04-14-mobile",
        "size": 351,
    },
    {
        "name": "sherpa-onnx-streaming-zipformer-en-2023-02-21-mobile",
        "size": 351,
    },
    {
        "name": "sherpa-onnx-streaming-zipformer-en-2023-06-21-mobile",
        "size": 349,
    },
    {
        "name": "sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20-mobile",
        "size": 331,
    },
    {
        "name": "sherpa-onnx-streaming-zipformer-small-bilingual-zh-en-2023-02-16-mobile",
        "size": 341,
    },
    {
        "name": "sherpa-onnx-streaming-zipformer-ar_en_id_ja_ru_th_vi_zh-2025-02-10",
        "size": 247,
    },
    {"name": "sherpa-onnx-streaming-zipformer-en-20M-2023-02-17", "size": 122},
    {"name": "sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23", "size": 70.6},
    {"name": "sherpa-onnx-streaming-zipformer-en-2023-02-21", "size": 380},
    {"name": "sherpa-onnx-streaming-zipformer-fr-2023-04-14", "size": 380},
    {"name": "sherpa-onnx-streaming-zipformer-en-2023-06-21", "size": 483},
    {"name": "sherpa-onnx-streaming-zipformer-korean-2024-06-16", "size": 399},
    # paraformers
    {"name": "sherpa-onnx-streaming-paraformer-bilingual-zh-en", "size": 999},
    {
        "name": "sherpa-onnx-streaming-paraformer-trilingual-zh-cantonese-en",
        "size": 999,
    },
    # wenet
    {"name": "sherpa-onnx-zh-wenet-aishell", "size": 339},
    {"name": "sherpa-onnx-zh-wenet-aishell2", "size": 339},
    {"name": "sherpa-onnx-en-wenet-librispeech", "size": 341},
    {"name": "sherpa-onnx-zh-wenet-wenetspeech", "size": 848},
    {"name": "sherpa-onnx-en-wenet-gigaspeech", "size": 890},
]


by_module_resource: dict[
    tuple[str, str], list[dict[str, float | int | str]]
] = {}


def find_matching(prefix: str, ext: str, dir: str):
    if not os.path.exists(dir):
        return ""
    x = [f for f in os.listdir(dir) if f.startswith(prefix) and f.endswith(ext)]
    x = list(x)
    x = sorted(x, key=lambda f: len(f))
    x = sorted(x, key=lambda f: 0 if "int8" in f else 1)
    x = sorted(x, key=lambda f: 0 if "streaming" in f else 1)

    if len(x) == 0:
        return ""
    return x[0]


class SherpaSTT:
    def __init__(
        self,
        name: str = "",
        model: str = "",
        model_cache_dir: str = "",
        **kwargs,
    ):
        import sherpa_onnx

        self.tag = ObjectTag(f"/stt/{name}")
        self.model_name = model
        self.default_speaker = 0

        model_dir = model

        cache_dir = model_cache_dir or os.path.expanduser(
            "~/.cache/sherpa-onnx-models/"
        )
        os.makedirs(cache_dir, exist_ok=True)

        model_dir = os.path.join(cache_dir, model_dir)
        download_script = f"""
        wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{model}.tar.bz2
        tar xvf {model}.tar.bz2
        rm {model}.tar.bz2
        """

        x = find_matching("tokens", ".txt", os.path.join(model_dir))
        if not x:
            a = alerts.Alert(
                "An STT Model is still downloading", priority="warning"
            )
            a.trip()
            subprocess.check_call(download_script, shell=True, cwd=cache_dir)
            a.clear()
            a.close()

        x = find_matching("tokens", ".txt", os.path.join(model_dir))
        if not x:
            raise RuntimeError("Downloading STT model failed")
        encoder = os.path.join(
            model_dir, find_matching("encoder", ".onnx", model_dir)
        )
        decoder = os.path.join(
            model_dir, find_matching("decoder", ".onnx", model_dir)
        )
        joiner = os.path.join(
            model_dir, find_matching("joiner", ".onnx", model_dir)
        )

        tokens = os.path.join(model_dir, "tokens.txt")

        model_file = os.path.join(
            model_dir, find_matching("model", ".onnx", model_dir)
        )

        if "zipformer" in model:
            recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
                tokens=tokens,
                encoder=encoder,
                decoder=decoder,
                joiner=joiner,
                num_threads=3,
                sample_rate=16000,
                feature_dim=80,
                enable_endpoint_detection=True,
                rule1_min_trailing_silence=2.4,
                rule2_min_trailing_silence=1.2,
                rule3_min_utterance_length=300,  # it essentially disables this rule
                decoding_method="modified_beam_search",
                provider="cpu",
                hotwords_file="",
                hotwords_score=1.5,
                blank_penalty=0.0,
            )
        elif "paraformer" in model:
            recognizer = sherpa_onnx.OnlineRecognizer.from_paraformer(
                tokens=tokens,
                encoder=encoder,
                decoder=decoder,
                num_threads=1,
                sample_rate=16000,
                feature_dim=80,
                enable_endpoint_detection=True,
                rule1_min_trailing_silence=2.4,
                rule2_min_trailing_silence=1.2,
                rule3_min_utterance_length=300,  # it essentially disables this rule
            )
        elif "wenet" in model:
            recognizer = sherpa_onnx.OnlineRecognizer.from_wenet_ctc(
                tokens=tokens,
                model=model_file,
                chunk_size=16,
                num_left_chunks=4,
                num_threads=3,
                provider="cpu",
                sample_rate=16000,
                feature_dim=80,
                decoding_method="greedy_search",
                rule1_min_trailing_silence=2.4,
                rule2_min_trailing_silence=1.2,
                rule3_min_utterance_length=300,  # it essentially disables this rule
            )
        else:
            raise RuntimeError(f"Unknown model type: {model}")

        self.last_result = None
        self.last_word = 0
        self.stt = recognizer
        self.stream = recognizer.create_stream()

        self.run = True

        self.run = True
        t = threading.Thread(
            target=self.streaming, daemon=True, name="SpeechRecognition"
        )
        t.start()

    def close(self):
        self.run = False

    def __del__(self):
        self.close()

    def streaming(self):
        import jack

        stream: list[bytes] = []
        self.client = client = jack.Client("my_client")
        port = client.inports.register("input_1")

        def process(_frame: int):
            frame = port.get_array().tolist()  # type: ignore
            if len(stream) < 128:
                stream.append(frame)

        client.set_process_callback(process)
        client.activate()

        while self.run:
            while stream:
                data = stream.pop(0)
                x = self.accept_waveform(data, client.samplerate)
                if x:
                    print(x)
            time.sleep(0.1)

    def accept_waveform(self, waveform: bytes, sample_rate: int = 16000):
        if self.stt is None:
            return

        self.stream.accept_waveform(waveform=waveform, sample_rate=sample_rate)

        while self.stt.is_ready(self.stream):
            self.stt.decode_stream(self.stream)

        is_endpoint = self.stt.is_endpoint(self.stream)

        result = self.stt.get_result(self.stream)

        if self.last_result != result:
            self.last_result = result
            self.last_word = time.monotonic()

        if is_endpoint or (time.monotonic() - self.last_word) > 4:
            self.stt.reset(self.stream)
            self.last_word = time.monotonic()
            if result:
                self.tag.value = {"stt": result}
                return result


# lock = threading.RLock()
# stt = SherpaSTT("sherpa-onnx-en-wenet-librispeech")
