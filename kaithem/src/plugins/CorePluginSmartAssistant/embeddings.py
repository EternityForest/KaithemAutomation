from typing import Any

from sklearn.metrics.pairwise import cosine_similarity


def similarity(a, b):
    return cosine_similarity(a, b)


# Document, retrieve, similarity
prefixes = {"qllama/multilingual-e5-small": ("passage: ", "query: ", "query: ")}


# def compute_mask(lst: list[str], prefix):
#     import ollama
#     import numpy

#     embeddings = ollama.embed(
#         # todo this only works with e5
#         model=model,
#         input=list([prefix + i[0] for i in lst]),
#     ).embeddings

#     arr = list(numpy.fromiter(i, numpy.float64) for i in embeddings)
#     std_dev = numpy.std(arr, axis=0)
#     median = numpy.median(std_dev)

#     mask = std_dev > median

#     for i in range(len(arr)):
#         arr[i] = arr[i] * mask

#     return mask, arr


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
                        + i[0].lower()
                        for i in lst
                    ]
                ),
            ).embeddings
        else:
            self.embeddings = model.encode(list([i[0] for i in lst]))

    def match(self, s: str) -> list[tuple[float, str, Any]]:
        s = s.lower()
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
            model = "qllama/multilingual-e5-small"
        else:
            from model2vec import StaticModel

            model = StaticModel.from_pretrained(
                "FlukeTJ/snowflake-arctic-embed-l-v2.0-m2v-distilled-256"
            )
        self.model = model

    def get_lookup(self, lst: list[tuple[str, Any]], retrieval=False):
        return EmbeddingsLookup(lst, self.model, retrieval=retrieval)
