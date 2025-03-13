from typing import Any, Sequence

import numpy
from sklearn.metrics.pairwise import cosine_similarity


def similarity(a, b):
    return cosine_similarity(a, b)


# Document, retrieve, similarity
prefixes = {"qllama/multilingual-e5-small": ("passage: ", "query: ", "query: ")}

scale_functions = {
    "qllama/multilingual-e5-small": lambda x: ((x - 0.8) * 6) ** 2,
    # "snowflake-arctic-embed:137m": lambda x: ((x - 0.75) * 4),
}


def cleanup(s: str):
    for i in ",./;'<>?[]{}-=_+~!@#$%^&*()\\|~`\"":
        s = s.replace(i, "")
    return s.lower()


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
        self.embeddings: Sequence[Sequence[float]] = []

        if isinstance(model, str):
            import ollama

            self.prefixes = prefixes.get(model, self.prefixes)
            to_embed = list(
                [
                    (self.prefixes[0] if retrieval else self.prefixes[2])
                    + cleanup(i[0])
                    for i in lst
                ]
            )
            print(to_embed)
            self.embeddings = ollama.embed(
                # todo this only works with e5
                model=model,
                input=to_embed,
            ).embeddings
        else:
            self.embeddings = model.encode(list([cleanup(i[0]) for i in lst]))

        if self.embeddings:
            first = list(self.embeddings[0])
            self.min_bound = numpy.fromiter(first, numpy.float64)
            self.max_bound = numpy.fromiter(first, numpy.float64)
            self.avgs = numpy.fromiter(first, numpy.float64)

            for i in self.embeddings:
                self.min_bound = numpy.minimum(self.min_bound, i)
                self.max_bound = numpy.maximum(self.max_bound, i)
                self.avgs += i

            self.avgs /= len(self.embeddings)
            self.ranges = self.max_bound - self.min_bound

    def set_membership(self, s):
        """This function determined by manual trial and error, I don't know the name
        of the algorithm"""
        if not self.embeddings:
            return 0.0

        qe = self.embed_one(s)

        # Constrain to our set bounding box
        constrained = numpy.clip(qe, self.min_bound, self.max_bound)

        # find difference from that point
        differences = abs(qe - self.avgs)

        # The less variable a point is, the more meaningful it is to be outside that
        importances = 1 / numpy.maximum(self.ranges, 0.1)

        # return similarity([differences], [numpy.zeros_like(differences)])[0][0]

        return 1 - (
            ((numpy.mean((differences * importances) ** 5)) * (1 / 5)) * 1024
        )
        # return similarity([qe * importances], [self.avgs * importances])[0][0]

        # return numpy.linalg.norm(differences)

        return similarity([constrained], [self.avgs])[0][0]

    def embed_one(self, s: str):
        if isinstance(self.model, str):
            import ollama

            s = self.prefixes[1] + s

            qe = ollama.embed(model=self.model, input=[s]).embeddings
        else:
            qe = self.model.encode([s])  # type: ignore

        return qe[0]

    def match(self, s: str) -> list[tuple[float, str, Any]]:
        s = cleanup(s)

        if not len(self.embeddings):
            return []

        qe = self.embed_one(s)
        sim = similarity([qe], self.embeddings)
        scale = scale_functions.get(self.model, lambda x: x)
        x = [
            (min(max(scale(v.item()), 0), 1), self.lst[i][0], self.lst[i][1])
            for i, v in enumerate(sim[0])
        ]

        return sorted(list(x), key=lambda x: x[0], reverse=True)


class EmbeddingsModel:
    def __init__(self, slow: bool = False) -> None:
        if slow:
            model = "snowflake-arctic-embed:137m"
        else:
            from model2vec import StaticModel

            model = StaticModel.from_pretrained(
                "FlukeTJ/snowflake-arctic-embed-l-v2.0-m2v-distilled-256"
            )
        self.model = model

    def get_lookup(self, lst: list[tuple[str, Any]], retrieval=False):
        return EmbeddingsLookup(lst, self.model, retrieval=retrieval)
