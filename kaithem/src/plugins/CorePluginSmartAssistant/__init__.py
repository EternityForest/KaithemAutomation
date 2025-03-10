# from collections.abc import Callable
# from rag3 import narrow_docs, ZimKnowledgeBase, search_documents
# from llm_backend import LLMSession

from typing import Any

from scullery import workers

from kaithem.api import plugin_interfaces, resource_types
from kaithem.src.plugins.CorePluginSTT import SherpaSTT, model_sources

from .builtin_skills import skills
from .embeddings import EmbeddingsModel
from .llm import LLMSession
from .skills import Skill


class Assistant(resource_types.ResourceTypeRuntimeObject):
    def __init__(self, data: dict[str, Any]):
        self.personality_docs: list[tuple[float, str, str]] = []
        self.skills: dict[str, Skill] = {}
        for i in skills:
            if i.name in data["enable_skills"]:
                self.skills[i.name] = i

        e: list[(tuple[str, Skill])] = []
        for i in self.skills:
            for j in self.skills[i].examples:
                e.append((j, self.skills[i]))

        self.embeddings = EmbeddingsModel()

        self.skill_lookup = self.embeddings.get_lookup(e)

        self.language: str = data["language"]

        if data["stt_model"]:
            self.stt = SherpaSTT(name=data["name"], model=data["stt_model"])
            self.stt.tag.subscribe(self.handle_stt)

        self.tts_model_id = data["tts_model"]
        self.tts_model: None | plugin_interfaces.TTSEngine = None

        self.get_tts_model()
        # self.knowledges: list[ZimKnowledgeBase] = []

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
        model.speak(s)

    def handle_stt(self, data, _t, _a):
        self.request(data["stt"])

    def request(self, req: str):
        print(f"Request: {req}")
        top = self.skill_lookup.match(req)[:3]
        if not top[0][0] > 0.4:
            return "Sorry, I don't understand that request"
        session = LLMSession()

        x = session.find_command(
            req, list([(i[2].command_str, i[2]) for i in top])
        )
        if x is None:
            return "Sorry, I don't understand that request"
        sk: Skill = x[0]
        result = sk.go(x[1], {"language": self.language})

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
            "enable_skills": {
                "type": "object",
                "properties": {i.name: {"type": "boolean"} for i in skills},
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
