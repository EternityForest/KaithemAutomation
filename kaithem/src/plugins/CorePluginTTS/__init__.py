from __future__ import annotations

import hashlib
import os
import subprocess
import threading
import time

# TODO: This needs to be moved to a core plugin
import icemedia.sound_player
from scullery import messagebus

from kaithem.api import modules, plugin_interfaces, settings
from kaithem.api.web import dialogs
from kaithem.src import alerts, module_actions, modules_state

plugin_metadata = {"provides": {"kaithem.core.tts": 0}}

piper_voices: list[dict[str, float | int | str]] = [
    {"name": "vits-piper-ar_JO-kareem-low", "size": 64},
    {"name": "vits-piper-ar_JO-kareem-medium", "size": 64.1},
    {"name": "vits-piper-ca_ES-upc_ona-medium", "size": 64.1},
    {"name": "vits-piper-ca_ES-upc_ona-x_low", "size": 25.3},
    {"name": "vits-piper-ca_ES-upc_pau-x_low", "size": 25.3},
    {"name": "vits-piper-cs_CZ-jirka-low", "size": 64.1},
    {"name": "vits-piper-cs_CZ-jirka-medium", "size": 64.1},
    {"name": "vits-piper-cy_GB-gwryw_gogleddol-medium", "size": 64.1},
    {"name": "vits-piper-da_DK-talesyntese-medium", "size": 64.1},
    {"name": "vits-piper-de_DE-eva_k-x_low", "size": 25.3},
    {"name": "vits-piper-de_DE-karlsson-low", "size": 64},
    {"name": "vits-piper-de_DE-kerstin-low", "size": 64},
    {"name": "vits-piper-de_DE-pavoque-low", "size": 64},
    {"name": "vits-piper-de_DE-ramona-low", "size": 64},
    {"name": "vits-piper-de_DE-thorsten-high", "size": 110},
    {"name": "vits-piper-de_DE-thorsten-low", "size": 64},
    {"name": "vits-piper-de_DE-thorsten-medium", "size": 64.1},
    {"name": "vits-piper-de_DE-thorsten_emotional-medium", "size": 76.5},
    {"name": "vits-piper-el_GR-rapunzelina-low", "size": 63.9},
    {"name": "vits-piper-en_GB-alan-low", "size": 64},
    {"name": "vits-piper-en_GB-alan-medium", "size": 64.1},
    {"name": "vits-piper-en_GB-alba-medium", "size": 64.1},
    {"name": "vits-piper-en_GB-aru-medium", "size": 76.6},
    {"name": "vits-piper-en_GB-cori-high", "size": 110},
    {"name": "vits-piper-en_GB-cori-medium", "size": 64.2},
    {"name": "vits-piper-en_GB-jenny_dioco-medium", "size": 64.1},
    {"name": "vits-piper-en_GB-northern_english_male-medium", "size": 64.1},
    {"name": "vits-piper-en_GB-semaine-medium", "size": 76.5},
    {"name": "vits-piper-en_GB-southern_english_female-low", "size": 64},
    {"name": "vits-piper-en_GB-southern_english_female-medium", "size": 76.5},
    {"name": "vits-piper-en_GB-southern_english_female_medium", "size": 76.5},
    {"name": "vits-piper-en_GB-southern_english_male-medium", "size": 76.6},
    {"name": "vits-piper-en_GB-sweetbbak-amy", "size": 110},
    {"name": "vits-piper-en_GB-vctk-medium", "size": 76.7},
    {"name": "vits-piper-en_US-amy-low", "size": 64},
    {"name": "vits-piper-en_US-amy-medium", "size": 64.1},
    {"name": "vits-piper-en_US-arctic-medium", "size": 76.6},
    {"name": "vits-piper-en_US-bryce-medium", "size": 64.2},
    {"name": "vits-piper-en_US-danny-low", "size": 64},
    {"name": "vits-piper-en_US-hfc_female-medium", "size": 64.1},
    {"name": "vits-piper-en_US-hfc_male-medium", "size": 64.1},
    {"name": "vits-piper-en_US-joe-medium", "size": 64.1},
    {"name": "vits-piper-en_US-john-medium", "size": 64.2},
    {"name": "vits-piper-en_US-kathleen-low", "size": 64},
    {"name": "vits-piper-en_US-kristin-medium", "size": 64.2},
    {"name": "vits-piper-en_US-kusal-medium", "size": 64.1},
    {"name": "vits-piper-en_US-l2arctic-medium", "size": 76.6},
    {"name": "vits-piper-en_US-lessac-high", "size": 110},
    {"name": "vits-piper-en_US-lessac-low", "size": 64},
    {"name": "vits-piper-en_US-lessac-medium", "size": 64.1},
    {"name": "vits-piper-en_US-libritts-high", "size": 125},
    {"name": "vits-piper-en_US-libritts_r-medium", "size": 78.2},
    {"name": "vits-piper-en_US-ljspeech-high", "size": 110},
    {"name": "vits-piper-en_US-ljspeech-medium", "size": 64.1},
    {"name": "vits-piper-en_US-norman-medium", "size": 64.1},
    {"name": "vits-piper-en_US-ryan-high", "size": 110},
    {"name": "vits-piper-en_US-ryan-low", "size": 64},
    {"name": "vits-piper-en_US-ryan-medium", "size": 64.1},
    {"name": "vits-piper-es-glados-medium", "size": 64.1},
    {"name": "vits-piper-es_ES-carlfm-x_low", "size": 25.3},
    {"name": "vits-piper-es_ES-davefx-medium", "size": 64.1},
    {"name": "vits-piper-es_ES-sharvard-medium", "size": 76.6},
    {"name": "vits-piper-es_MX-ald-medium", "size": 64.1},
    {"name": "vits-piper-es_MX-claude-high", "size": 64.1},
    {"name": "vits-piper-fa-haaniye_low", "size": 64},
    {
        "name": "vits-piper-fa_en-rezahedayatfar-ibrahimwalk-medium",
        "size": 64.1,
    },
    {"name": "vits-piper-fa_IR-amir-medium", "size": 64.1},
    {"name": "vits-piper-fa_IR-gyro-medium", "size": 64.1},
    {"name": "vits-piper-fi_FI-harri-low", "size": 64},
    {"name": "vits-piper-fi_FI-harri-medium", "size": 64},
    {"name": "vits-piper-fr_FR-gilles-low", "size": 64},
    {"name": "vits-piper-fr_FR-siwis-low", "size": 25.3},
    {"name": "vits-piper-fr_FR-siwis-medium", "size": 64.1},
    {"name": "vits-piper-fr_FR-tjiho-model1", "size": 64.1},
    {"name": "vits-piper-fr_FR-tjiho-model2", "size": 64.1},
    {"name": "vits-piper-fr_FR-tjiho-model3", "size": 64.1},
    {"name": "vits-piper-fr_FR-tom-medium", "size": 64.1},
    {"name": "vits-piper-fr_FR-upmc-medium", "size": 76.7},
    {"name": "vits-piper-hu_HU-anna-medium", "size": 64.1},
    {"name": "vits-piper-hu_HU-berta-medium", "size": 64.1},
    {"name": "vits-piper-hu_HU-imre-medium", "size": 64.1},
    {"name": "vits-piper-is_IS-bui-medium", "size": 64.1},
    {"name": "vits-piper-is_IS-salka-medium", "size": 64.2},
    {"name": "vits-piper-is_IS-steinn-medium", "size": 64.2},
    {"name": "vits-piper-is_IS-ugla-medium", "size": 64.2},
    {"name": "vits-piper-it_IT-paola-medium", "size": 64.1},
    {"name": "vits-piper-it_IT-riccardo-x_low", "size": 25.2},
    {"name": "vits-piper-ka_GE-natia-medium", "size": 64.1},
    {"name": "vits-piper-kk_KZ-iseke-x_low", "size": 25.3},
    {"name": "vits-piper-kk_KZ-issai-high", "size": 123},
    {"name": "vits-piper-kk_KZ-raya-x_low", "size": 25.3},
    {"name": "vits-piper-lb_LU-marylux-medium", "size": 64.1},
    {"name": "vits-piper-lv_LV-aivars-medium", "size": 64.1},
    {"name": "vits-piper-ne_NP-google-medium", "size": 76.6},
    {"name": "vits-piper-ne_NP-google-x_low", "size": 31.6},
    {"name": "vits-piper-nl_BE-nathalie-medium", "size": 64.1},
    {"name": "vits-piper-nl_BE-nathalie-x_low", "size": 25.2},
    {"name": "vits-piper-nl_BE-rdh-medium", "size": 63.9},
    {"name": "vits-piper-nl_BE-rdh-x_low", "size": 25.2},
    {"name": "vits-piper-no_NO-talesyntese-medium", "size": 64.1},
    {"name": "vits-piper-pl_PL-darkman-medium", "size": 64.1},
    {"name": "vits-piper-pl_PL-gosia-medium", "size": 64},
    {"name": "vits-piper-pl_PL-mc_speech-medium", "size": 64.1},
    {"name": "vits-piper-pt_BR-edresson-low", "size": 64},
    {"name": "vits-piper-pt_BR-faber-medium", "size": 64.1},
    {"name": "vits-piper-pt_PT-tugao-medium", "size": 64.1},
    {"name": "vits-piper-ro_RO-mihai-medium", "size": 64.1},
    {"name": "vits-piper-ru_RU-denis-medium", "size": 64.1},
    {"name": "vits-piper-ru_RU-dmitri-medium", "size": 64.1},
    {"name": "vits-piper-ru_RU-irina-medium", "size": 64.1},
    {"name": "vits-piper-ru_RU-ruslan-medium", "size": 64.1},
    {"name": "vits-piper-sk_SK-lili-medium", "size": 64.1},
    {"name": "vits-piper-sl_SI-artur-medium", "size": 63.9},
    {"name": "vits-piper-sr_RS-serbski_institut-medium", "size": 76.6},
    {"name": "vits-piper-sv_SE-nst-medium", "size": 64},
    {"name": "vits-piper-sw_CD-lanfrica-medium", "size": 64.1},
    {"name": "vits-piper-tr_TR-dfki-medium", "size": 64.1},
    {"name": "vits-piper-tr_TR-fahrettin-medium", "size": 64.1},
    {"name": "vits-piper-tr_TR-fettah-medium", "size": 64.1},
    {"name": "vits-piper-uk_UA-lada-x_low", "size": 25.3},
    {"name": "vits-piper-uk_UA-ukrainian_tts-medium", "size": 76.6},
    {"name": "vits-piper-vi_VN-25hours_single-low", "size": 64},
    {"name": "vits-piper-vi_VN-vais1000-medium", "size": 64},
    {"name": "vits-piper-vi_VN-vivos-x_low", "size": 31.8},
    {"name": "vits-piper-zh_CN-huayan-medium", "size": 64.1},
    {"name": "kokoro-en-v0_19", "size": 305},
    {"name": "kokoro-int8-multi-lang-v1_1", "size": 140},
    {"name": "kokoro-multi-lang-v1_0", "size": 333},
    {"name": "kokoro-multi-lang-v1_1", "size": 348},
    {"name": "kokoro-en-v0_19", "size": 305},
]

settings.set_description(
    "core_plugin_tts/default_model",
    """Setting this will cause the TTS to be downloaded if not present.
    Cori, libritts, and vctk recommended for english.""",
)

for i in piper_voices:
    settings.add_suggestion(
        "core_plugin_tts/default_model",
        str(i["name"]),
        f"{i['name']} {i['size']}MB",
    )

models: dict[str, PiperTTS | KokoroTTS] = {}
default_tts = None


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


class PiperTTS(plugin_interfaces.TTSEngine):
    def __init__(
        self,
        model: str = "vits-piper-en_US-libritts_r-medium",
        model_cache_dir: str = "",
        **kwargs,
    ):
        import sherpa_onnx

        self.name = model
        self.default_speaker = 0

        selected_model_dir = model

        model2 = model.replace("vits-piper-", "")

        cache_dir = model_cache_dir or os.path.expanduser(
            "~/.cache/sherpa-onnx-models/"
        )
        os.makedirs(cache_dir, exist_ok=True)

        selected_model_dir = os.path.join(cache_dir, selected_model_dir)
        download_script = f"""
        wget https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/{model}.tar.bz2
        tar xvf {model}.tar.bz2
        rm {model}.tar.bz2
        """
        if not os.path.exists(
            os.path.join(selected_model_dir, f"{model2}.onnx")
        ):
            a = alerts.Alert(
                "A TTS Model is still downloading", priority="warning"
            )
            a.trip()
            subprocess.check_call(download_script, shell=True, cwd=cache_dir)
            a.clear()
            a.close()

        if not os.path.exists(
            os.path.join(selected_model_dir, f"{model2}.onnx")
        ):
            raise RuntimeError("Downloading Piper model failed")

        tts_config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                    model=os.path.join(selected_model_dir, f"{model2}.onnx"),
                    tokens=os.path.join(selected_model_dir, "tokens.txt"),
                    data_dir=os.path.join(selected_model_dir, "espeak-ng-data"),
                    lexicon="",
                )
            )
        )

        self.tts = sherpa_onnx.OfflineTts(tts_config)

        models[model] = self

    def synth(self, s: str, speed: float = 1, sid: int = -1, file: str = ""):
        import soundfile as sf

        if sid == -1:
            sid = self.default_speaker
        if not file:
            file = self.get_fn(s, sid, speed)
            if os.path.isfile(file):
                return file

        audio = self.tts.generate("--..." + s, sid=sid, speed=speed)

        if len(audio.samples) == 0:
            raise RuntimeError(
                "Error in generating audios. Please read previous error messages."
            )

        sf.write(
            file,
            audio.samples,
            samplerate=audio.sample_rate,
            subtype="MPEG_LAYER_III",
        )
        return file

    def speak(
        self,
        s: str,
        speed: float = 1,
        sid: int = 220,
        device: str = "",
        volume: float = 1,
    ):
        f = self.synth(s, speed=speed, sid=sid)
        icemedia.sound_player.play_sound(
            f, handle=s, volume=volume, output=device
        )
        for i in range(100):
            time.sleep(0.5)
            if not icemedia.sound_player.is_playing(s):
                break

    def clean_tts_cache(self):
        x = []
        for i in os.listdir("/dev/shm/tts-cache"):
            if i.endswith((".ogg", ".wav", ".mp3")):
                t = os.stat(os.path.join("/dev/shm/tts-cache", i)).st_mtime
                x.append((t, i))
        x.sort()

        while len(x) > 200:
            i = x.pop(0)
            os.remove(os.path.join("/dev/shm/tts-cache", i[1]))

    def get_fn(self, s: str, sid, speed) -> str:
        hash = (
            hashlib.sha256(f"{self.name} {sid} {speed} {s}".encode())
            .hexdigest()
            .lower()[:12]
        )

        fn = s[:16].replace("\n", "_").replace(" ", "_")
        for i in ",./;'[]~`!@#$%^&*()_+-=<>?:\"{}\\":
            fn = fn.replace(i, "")
        fn = fn + hash + ".mp3"

        c = "/dev/shm/tts-cache"
        os.makedirs(c, exist_ok=True)

        fn = os.path.join(c, fn)
        if os.path.exists(fn):
            os.utime(fn, (time.time(), time.time()))
        else:
            self.clean_tts_cache()
        return fn


class KokoroTTS(PiperTTS):
    def __init__(
        self,
        model: str = "",
        model_cache_dir: str = "",
        **kwargs,
    ):
        import sherpa_onnx

        self.name = model
        self.default_speaker = 0

        selected_model_dir = model

        cache_dir = model_cache_dir or os.path.expanduser(
            "~/.cache/sherpa-onnx-models/"
        )
        os.makedirs(cache_dir, exist_ok=True)

        selected_model_dir = os.path.join(cache_dir, selected_model_dir)
        download_script = f"""
        wget https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/{model}.tar.bz2
        tar xvf {model}.tar.bz2
        rm {model}.tar.bz2
        """

        if not find_matching("model", "onnx", selected_model_dir):
            a = alerts.Alert(
                "A TTS Model is still downloading", priority="warning"
            )
            a.trip()
            subprocess.check_call(download_script, shell=True, cwd=cache_dir)
            a.clear()
            a.close()

        if not find_matching("model", "onnx", selected_model_dir):
            raise RuntimeError("Downloading Piper model failed")

        lexicon = [
            os.path.join(selected_model_dir, i)
            for i in os.listdir(selected_model_dir)
            if i.startswith("lexicon-")
        ]
        lexicon = list(lexicon)
        lexicon.sort(key=lambda s: 0 if "-en" in s else 1)

        tts_config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                    model=os.path.join(
                        selected_model_dir,
                        find_matching("model", "onnx", selected_model_dir),
                    ),
                    voices=os.path.join(selected_model_dir, "voices.bin"),
                    tokens=os.path.join(selected_model_dir, "tokens.txt"),
                    data_dir=os.path.join(selected_model_dir, "espeak-ng-data"),
                    dict_dir=os.path.join(selected_model_dir, "dict"),
                    lexicon=",".join(lexicon),
                )
            )
        )

        self.tts = sherpa_onnx.OfflineTts(tts_config)

        models[model] = self


lock = threading.RLock()


class TTSInterface(plugin_interfaces.TTSAPI):
    def get_model(self, model: str = "", timeout: float = 5):
        global default_tts
        speaker = 0

        if lock.acquire(timeout=timeout):
            rl = True
            try:
                if model == "":
                    if default_tts is not None:
                        return default_tts
                    model = settings.get_val("core_plugin_tts/default_model")
                    speaker = int(
                        settings.get_val("core_plugin_tts/default_speaker") or 0
                    )

                if not model:
                    return None

                try:
                    return models[model]
                except KeyError:
                    pass

                if model not in models:

                    def f():
                        with lock:
                            if model.startswith("kokoro"):
                                m = KokoroTTS(model=model)
                            else:
                                m = PiperTTS(model=model)
                            m.default_speaker = speaker
                            models[model] = m

                    lock.release()
                    rl = False

                    threading.Thread(target=f).start()

                    for i in range(int(timeout * 10)):
                        time.sleep(0.1)
                        if model in models:
                            return models[model]
                    return None
            finally:
                if rl:
                    lock.release()
        else:
            return None


api = TTSInterface()
plugin_services = [api]


def on_key_change(topic: str, key):
    global default_tts

    if key == "core_plugin_tts/default_model":
        current = settings.get_val("core_plugin_tts/default_model")
        if default_tts is not None:
            if default_tts.name == current:
                return

            default_tts.close()
        default_tts = api.get_model(current)

    if key == "core_plugin_tts/default_speaker":
        current = settings.get_val("core_plugin_tts/default_speaker") or 0
        if default_tts is not None:
            default_tts.default_speaker = int(current)


messagebus.subscribe("/system/config/changed", on_key_change)
api.get_model()


class TTSAction(module_actions.ModuleAction):
    title = "Speech Synthesis"

    def step(self, **kwargs):
        global default_tts
        super().step(**kwargs)

        if "string" not in kwargs:
            s = dialogs.SimpleDialog("Speech Synthesis")
            s.text_input(
                "string",
                title="Text",
                suggestions=[
                    (
                        """Amidst the mists and fiercest frosts,
 with stoutest wrists and loudest boasts,
 he thrusts his fists against the posts,
 and still insists he sees the ghosts.""",
                        "Demo",
                    )
                ],
            )

            s.text_input(
                "model",
                title="TTS Model",
                default=settings.get_val("core_plugin_tts/default_model")
                or "kokoro-en-v0_19",
                suggestions=list(
                    [(str(i["name"]), str(i["size"])) for i in piper_voices]
                ),
            )
            s.text_input("sid", title="Speaker ID", default="0")
            s.text_input("speed", title="Speed", default="1")
            s.text_input("name", title="Name", default="")
            s.text(
                "If empty, filename is generated from the text and settings."
            )

            s.submit_button("Create")
            return s.render(self.get_step_target())

        else:
            with modules.modules_lock:
                dir = modules.filename_for_file_resource(
                    self.context["module"], "media/tts"
                )

            s = kwargs["string"]
            m = kwargs["model"]
            sid = int(kwargs["sid"])
            t = time.strftime("%Y-%m-%d-%H-%M-%S")

            name = (
                kwargs["name"].strip()
                or f"{s[:32].replace("\n", "_").replace(" ", "_")}_{sid}_{m}_{t}.mp3"
            )

            if not name.endswith(".mp3"):
                name += ".mp3"

            fn = os.path.join(
                dir,
                name,
            )

            os.makedirs(os.path.dirname(fn), exist_ok=True)

            model = api.get_model(m, 240)
            assert model
            model.synth(s, float(kwargs["speed"]), int(kwargs["sid"]), fn)
            modules_state.importFiledataFolderStructure(self.context["module"])

        return self.close()


module_actions.add_action(TTSAction)
