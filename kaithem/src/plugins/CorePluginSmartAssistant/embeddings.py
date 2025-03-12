from typing import Any

from sklearn.metrics.pairwise import cosine_similarity


def similarity(a, b):
    return cosine_similarity(a, b)


# Document, retrieve, similarity
prefixes = {"qllama/multilingual-e5-small": ("passage: ", "query: ", "query: ")}


class EmbeddingsLookup:
    def __init__(
        self, lst: list[tuple[str, Any]], model: Any, retrieval=True
    ) -> None:
        self.model = model  # type: ignore
        self.lst = lst
        self.retrieval = retrieval

        self.prefixes = ("", "", "")

        if isinstance(model, str):
            import ollama

            self.prefixes = prefixes.get(model, self.prefixes)

            self.embeddings = ollama.embed(
                # todo this only works with e5
                model=model,
                input=list(
                    [
                        (self.prefixes[0] if retrieval else self.prefixes[2])
                        + i[0]
                        for i in lst
                    ]
                ),
            ).embeddings
        else:
            self.embeddings = model.encode(list([i[0] for i in lst]))

    def match(self, s: str) -> list[tuple[float, str, Any]]:
        if isinstance(self.model, str):
            import ollama

            s = self.prefixes[1] + s

            qe = ollama.embed(model=self.model, input=[s]).embeddings
        else:
            qe = self.model.encode([s])  # type: ignore

        if not len(self.embeddings):
            return []

        sim = similarity(qe, self.embeddings)

        x = [
            (max(v.item(), 0), self.lst[i][0], self.lst[i][1])
            for i, v in enumerate(sim[0])
        ]

        return sorted(list(x), key=lambda x: x[0], reverse=True)


class EmbeddingsModel:
    def __init__(self, slow: bool = False) -> None:
        if slow:
            model = "Definity/granite-embedding-278m-multilingual-Q8_0"
        else:
            from model2vec import StaticModel

            model = StaticModel.from_pretrained(
                "FlukeTJ/snowflake-arctic-embed-l-v2.0-m2v-distilled-256"
            )
        self.model = model

    def get_lookup(self, lst: list[tuple[str, Any]], retrieval=False):
        return EmbeddingsLookup(lst, self.model, retrieval=retrieval)


em = EmbeddingsModel(slow=False)
x = em.get_lookup(
    [
        ("What time is it in Florida?", 0),
        ("What do you know about Dracula's Castle", 0),
        ("What do you sell?", 0),
        ("Where is the tavern?", 0),
    ],
    retrieval=True,
)

print(x.match("What's up with the castle?"))


print(x.match("Where does the vampire live?"))
print(x.match("What's for sale?"))
print(x.match("Do you have wine?"))
print(x.match("Whta's the time in Florida??"))
