import time
from collections.abc import Callable

# from rag3 import narrow_docs, ZimKnowledgeBase, search_documents
# from llm_backend import LLMSession
from typing import Any

from scullery import workers

from kaithem.api import plugin_interfaces, resource_types
from kaithem.src.plugins.CorePluginSTT import SherpaSTT, model_sources

from .builtin_skills import available_skills
from .embeddings import EmbeddingsModel
from .llm import LLMSession
from .skills import OptionMatchSkill, Skill


def make_speak_func(assistant, text) -> Callable[..., str]:
    def f(*_a, **_k):
        return text

    return f


class Assistant(resource_types.ResourceTypeRuntimeObject):
    def __init__(self, data: dict[str, Any]):
        self.personality_docs: list[tuple[float, str, str]] = []
        self.skills: dict[str, Skill] = {}
        for i in available_skills:
            if i.name in data["enable_skills"]:
                self.skills[i.name] = i

        e: list[(tuple[str, Skill])] = []
        for i in self.skills:
            for j in self.skills[i].examples:
                e.append((j, self.skills[i]))

        for i in data.get("menu_options", []):
            for j in i["example_sentences"]:
                e.append(
                    (
                        j,
                        OptionMatchSkill(
                            examples=[j],
                            handler=make_speak_func(self, i["response"]),
                        ),
                    )
                )

        self.embeddings = EmbeddingsModel(slow=True)

        self.skill_lookup = self.embeddings.get_lookup(e, retrieval=False)

        self.language: str = data["language"]

        if data["stt_model"]:
            self.stt = SherpaSTT(name=data["name"], model=data["stt_model"])
            self.stt.tag.subscribe(self.handle_stt)

        self.tts_model_id = data["tts_model"]
        self.tts_model: None | plugin_interfaces.TTSEngine = None

        self.get_tts_model()
        # self.knowledges: list[ZimKnowledgeBase] = []

    def close(self):
        if self.stt:
            self.stt.close()

    def get_tts_model(self):
        if not self.tts_model_id:
            return

        def f():
            self.tts_model = plugin_interfaces.TTSAPI.get_providers()[
                0
            ].get_model(self.tts_model_id, timeout=240)

        workers.do(f)

    def respond(self, s: str):
        print(f"Responding: {s}")
        model = self.tts_model
        if model is None:
            self.get_tts_model()
            print("No TTS model available yet")
            return

        if self.stt:
            self.stt.mute += 1

        model.speak(s)
        time.sleep(0.15)
        if self.stt:
            self.stt.mute -= 1

    def handle_stt(self, data, _t, _a):
        def f():
            self.request(data["stt"])

        workers.do(f)

    def request(self, req: str):
        if not req.strip():
            return

        if not len(req) > 5:
            return

        req = req.lower()

        print(f"Request: {req}")
        top = self.skill_lookup.match(req)

        # Eliminate duplicates
        top_2 = {id(i[2]): (i[0], i[1], i[2]) for i in top}

        top = list(top_2.values())
        top.sort(key=lambda x: x[0], reverse=True)
        top = top[:3]

        if not top:
            return
        print(top)
        if not top[0][0] > 0.4:
            return

        # Handle the direct match based skills.
        if top[0][0] > 0.98 and not top[0][2].command:
            result = top[0][2].go(context={"language": self.language})
            t = result.execute()
            self.respond(t)
            return

        session = LLMSession()

        # Some don't have command_str like the OptionMatchSkill
        x = session.find_command(
            req,
            list([(i[2].command, i[2]) for i in top if i[2].command]),
        )

        if x is None:
            self.respond("Sorry, I don't understand that request")
            return
        sk: Skill = x[0]
        result = sk.go(**x[1], context={"language": self.language})

        t = result.execute()

        self.respond(t)

    def add_personality_doc(self, title: str, content: str, boost: float = 1.0):
        self.personality_docs.append((boost, title, content))

    # def add_zim_knowledge(self, zimfile: str):
    #     self.knowledges.append(ZimKnowledgeBase(zimfile))

    # def ask_knowledge(self, q: str) -> str:
    #     q = q.lower()

    #     raw_docs: list[tuple[str, str]] = []
    #     for i in self.knowledges:
    #         raw_docs.extend(i.search(q))

    #     docs: list[tuple[float, str, str]] = narrow_docs(raw_docs, q)

    #     docs += list(self.personality_docs)

    #     x = search_documents(docs, q)

    #     session = LLMSession()
    #     return session.document_rag(q, x)


def schema():
    tts_models = plugin_interfaces.TTSAPI.get_providers()[
        0
    ].list_available_models()
    return {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
            },
            "language": {
                "type": "string",
                "enum": ["en", "de", "es", "fr", "it", "pt", "ru", "zh"],
            },
            "stt_model": {
                "type": "string",
                "enum": list([i["name"] for i in model_sources]) + [""],
            },
            "tts_model": {
                "type": "string",
                "enum": list([i["name"] for i in tts_models]) + [""],
            },
            "llm_model": {
                "type": "string",
                "enum": ["gemma3:4b", "qwen2.5-coder:0.5b"],
            },
            "menu_options": {
                "type": "array",
                "description": "A list of simple menu options to detect and respond to.",
                "items": {
                    "type": "object",
                    "properties": {
                        "example_sentences": {
                            "type": "array",
                            "title": "Example Sentences",
                            "description": "A list of example sentences that would trigger the option",
                            "items": {"type": "string"},
                        },
                        "response": {
                            "type": "string",
                            "title": "Response",
                            "description": "Simple voice response",
                        },
                    },
                },
            },
            "enable_skills": {
                "type": "object",
                "properties": {
                    i.name: {"type": "boolean"} for i in available_skills
                },
            },
        },
        "required": ["enable_skills", "name", "stt_model", "tts_model"],
    }


default = {
    "enable_skills": {},
    "name": "default_assistant",
    "stt_model": "",
    "tts_model": "",
    "language": "en",
}

resource_types.resource_type_from_schema(
    "smart-assistant",
    "Smart Assistant",
    "assistant",
    schema,
    Assistant,
    default=default,
)
