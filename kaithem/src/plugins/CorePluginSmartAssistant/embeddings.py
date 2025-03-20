from typing import Any, Iterable, Sequence

import numpy as np
from scipy.spatial import distance


def cartesian_to_polar(vector):
    """
    Converts a Cartesian vector to higher-dimensional polar coordinates.

    Args:
        vector (numpy.ndarray): A Cartesian vector.

    Returns:
        numpy.ndarray: An array containing the radius and angles
                         representing the polar coordinates.
    """
    vector = np.array(vector)
    num_dims = vector.shape[0]
    polar_coords = np.zeros(num_dims)

    # Calculate radius
    polar_coords[0] = np.linalg.norm(vector)

    # Calculate angles
    for i in range(1, num_dims):
        # Project vector onto the plane formed by the i-th axis and the origin
        projection = vector[: i + 1]

        # Calculate angle with respect to the previous axes
        polar_coords[i] = np.arctan2(
            projection[-1], np.linalg.norm(projection[:-1])
        )

    return polar_coords


def similarity(a, b):
    return [list([1 - distance.cosine(a[0], i) for i in b])]

    # return [list([1 - numpy.mean(a[0] - i) for i in b])]

    # return cosine_similarity(a, b)


# Document, retrieve, similarity
prefixes = {
    "qllama/multilingual-e5-small": ("passage: ", "query: ", "query: "),
    "yxchia/multilingual-e5-base:Q8_0": ("passage: ", "query: ", "query: "),
    "qllama/multilingual-e5-small:q4_k_m": ("passage: ", "query: ", "query: "),
    "snowflake-arctic-embed:137m": ("", "query: ", ""),
}

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

# import time


class EmbeddingsLookup:
    def __init__(
        self, lst: Iterable[tuple[str, Any]], model: Any, retrieval=True
    ) -> None:
        self.model = model  # type: ignore
        self.lst = list(lst)
        self.retrieval = retrieval

        self.prefixes = ("", "", "")
        self.embeddings: Sequence[Sequence[float]] = []

        # print(f"Matching against {len(self.lst)} records with {self.model}")
        # t = time.time()
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
            self.embeddings = ollama.embed(
                # todo this only works with e5
                model=model,
                input=to_embed,
            ).embeddings
        else:
            self.embeddings = model.encode(list([cleanup(i[0]) for i in lst]))
        # print(f"Done in {time.time() - t}")

        # if len(self.embeddings) > 0:
        #     first = list(self.embeddings[0])
        #     self.avgs = numpy.median(self.embeddings, axis=0)
        #     self.variance = numpy.zeros_like(first)
        #     #     self.avgs += i

        #     # self.avgs /= len(self.embeddings)

        #     for i in self.embeddings:
        #         self.variance += abs(self.avgs - i)
        #     # self.variance = numpy.sqrt(self.variance)
        #     self.variance = self.variance / len(self.embeddings)

    #         x = 0
    #         for i in lst:
    #             x += self.set_membership_raw(i[0])
    #         x /= len(lst)

    #         self.avg_set_membership = x

    # def set_membership(self, s):
    #     closest = self.embed_one(self.match(s)[0][1])
    #     return closest[0], self.set_membership_raw(s)

    # def set_membership_raw(self, s):
    #     """This function doesn't really work"""

    #     if not len(self.embeddings):
    #         return 0.0

    #     closest = numpy.array(self.embed_one(self.match(s)[0][1]))

    #     qe = numpy.array(self.embed_one(s))

    #     # The less variable a point is, the more meaningful it is to be outside that
    #     importances = 1 / numpy.maximum(self.variance**5, 0.00000000000000001)
    #     # constrained = numpy.clip(qe, self.min_bound, self.max_bound)

    #     x = distance.cosine(qe, self.avgs, importances)

    #     return 1 / x

    # # Constrain to our set bounding box

    # # find difference from that point

    # # return similarity([differences], [numpy.zeros_like(differences)])[0][0]

    # return 1 - ((numpy.mean((differences * importances) ** 3)) * (1 / 3))
    # # return similarity([qe * importances], [self.avgs * importances])[0][0]

    # # return numpy.linalg.norm(differences)

    # return similarity([constrained], [self.avgs])[0][0]

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
            model = "yxchia/multilingual-e5-base:Q8_0"
        else:
            from model2vec import StaticModel

            model = StaticModel.from_pretrained(
                "FlukeTJ/snowflake-arctic-embed-l-v2.0-m2v-distilled-256"
            )
        self.model = model

    def get_lookup(self, lst: list[tuple[str, Any]], retrieval=False):
        return EmbeddingsLookup(lst, self.model, retrieval=retrieval)
