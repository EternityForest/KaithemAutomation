import os
import time
from collections.abc import Callable

# from rag3 import narrow_docs, ZimKnowledgeBase, search_documents
# from llm_backend import LLMSession
from typing import Any

from scullery import workers

from kaithem.api import modules, plugin_interfaces, resource_types
from kaithem.src.plugins.CorePluginSTT import SherpaSTT, model_sources

from .builtin_skills import available_skills
from .embeddings import EmbeddingsModel
from .llm import LLMSession
from .rag import ZimKnowledgeBase, narrow_docs, search_documents
from .skills import OptionMatchSkill, SimpleSkillResponse, Skill


class KnowledgeSkill(Skill):
    def go(self, context: dict[str, Any], **kwargs) -> SimpleSkillResponse:
        assistant = context["assistant_object"]
        r = assistant.ask_knowledge(kwargs["question"])
        return SimpleSkillResponse(r)


s = KnowledgeSkill(
    examples=[
        "Where is Georgia?",
        "Who discovered Fluorine?",
        "Where is the Eiffel Tower?",
        "How many states are there in the US?",
        "How tall is Mount Everest?",
    ],
    command="answer-question",
    schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "const": "answer-question"},
            "query": {"type": "question"},
        },
        "required": ["command", "question"],
    },
)
available_skills.append(s)


def make_speak_func(assistant, text) -> Callable[..., str]:
    def f(*_a, **_k):
        return text

    return f


class Assistant(resource_types.ResourceTypeRuntimeObject):
    def __init__(self, module: str, resource: str, data: dict[str, Any]):
        self.personality_docs: list[tuple[float, str, str]] = []
        self.skills: dict[str, Skill] = {}
        self.embeddings = EmbeddingsModel(slow=True)

        self.wake_words = data.get("wake_words", [])

        self.knowledges: list[ZimKnowledgeBase] = []
        self.fast_embed = EmbeddingsModel(slow=False)

        wd = modules.filename_for_file_resource(module, resource)
        wd = os.path.dirname(wd)

        for i in data.get("zim_knowledge", []):
            i = os.path.expanduser(i)
            i = os.path.join(wd, i)
            self.knowledges.append(ZimKnowledgeBase(i))

        for i in available_skills:
            if i.name in data["enable_skills"]:
                self.skills[i.name] = i

        e: list[(tuple[str, Skill])] = []
        for i in self.skills:
            self.skills[i].do_embeddings(self.embeddings)
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
                            match_threshold=i.get("match_threshold", 0.95),
                        ),
                    )
                )

        self.skill_lookup = self.embeddings.get_lookup(e, retrieval=True)

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

        wakeword = True

        if self.wake_words:
            wakeword = False
            for i in self.wake_words:
                if i in s:
                    wakeword = True
                    s = s.split(i)[-1].strip()

        if not wakeword:
            return

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
        top_2 = {}

        for i in top:
            if i[1] not in top_2:
                top_2[i[1]] = i
            elif i[0] > top_2[i[1]][0]:
                top_2[i[1]] = i

        top = list(top_2.values())
        top.sort(key=lambda x: x[0], reverse=True)
        print(top)

        top = top[:3]

        if not top:
            return

        if not top[0][0] > 0.4:
            return

        # Handle the direct match based skills.
        if top[0][0] > top[0][2].match_threshold and not top[0][2].command:
            result = top[0][2].go(context={"language": self.language})
            t = result.execute()
            self.respond(t)
            return

        # # Further narrow it down with this set membership checker thing.
        # top = [i for i in top if i[2].lookup.set_membership(req) > 0.8]

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
        result = sk.go(
            **x[1],
            context={"language": self.language, "assistant_object": self},
        )

        t = result.execute()

        self.respond(t)

    def add_personality_doc(self, title: str, content: str, boost: float = 1.0):
        self.personality_docs.append((boost, title, content))

    def add_zim_knowledge(self, zimfile: str):
        self.knowledges.append(ZimKnowledgeBase(zimfile))

    def ask_knowledge(self, q: str) -> str:
        q = q.lower()

        raw_docs: list[tuple[str, str]] = []
        for i in self.knowledges:
            raw_docs.extend(i.search(q))

        docs: list[tuple[float, str, str]] = narrow_docs(raw_docs, q)[:4]

        docs += list(self.personality_docs)

        x = search_documents(docs, q, self.fast_embed, self.embeddings)

        session = LLMSession()
        return session.document_rag(q, x)


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
            "wake_words": {
                "title": "Wake Words",
                "description": "For best reliability, include a few common sound-alikes for the wake word.",
                "type": "array",
                "items": {"type": "string"},
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
                "enum": [" Gemma3:1b", "Gemma3:4b", "qwen2.5-coder:0.5b"],
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
                        "match_threshold": {
                            "type": "number",
                            "title": "Match Threshold",
                            "description": "How closely a sentence must match the example sentences to trigger it",
                            "minimum": 0,
                            "maximum": 1,
                            "default": 0.9,
                        },
                        "response": {
                            "type": "string",
                            "title": "Response",
                            "description": "Simple voice response",
                        },
                    },
                },
            },
            "zim_knowledge": {
                "type": "array",
                "items": {"type": "string"},
                "title": "Zim Knowledge",
                "description": """List of zim files to use for the knowledge-search skill.
Knowledge search may be slow""",
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
