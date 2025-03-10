from typing import Any

from sklearn.metrics.pairwise import cosine_similarity


def similarity(a, b):
    return cosine_similarity(a, b)


class EmbeddingsLookup:
    def __init__(self, lst: list[tuple[str, Any]], model=Any) -> None:
        self.model = model  # type: ignore
        self.lst = lst
        self.embeddings = model.encode(list([i[0] for i in lst]))

    def match(self, s: str) -> list[tuple[float, str, Any]]:
        qe = self.model.encode([s])  # type: ignore
        sim = similarity(qe, self.embeddings)
        x = [
            (max(v.item(), 0), self.lst[i][0], self.lst[i][1])
            for i, v in enumerate(sim[0])
        ]

        return sorted(list(x), key=lambda x: x[0], reverse=True)


class EmbeddingsModel:
    def __init__(self, slow: bool = False) -> None:
        if slow:
            raise NotImplementedError
            # m = slow_model
        else:
            from model2vec import StaticModel

            model = StaticModel.from_pretrained(
                "FlukeTJ/snowflake-arctic-embed-l-v2.0-m2v-distilled-256"
            )
            self.model = model

    def get_lookup(self, lst: list[tuple[str, Any]]):
        return EmbeddingsLookup(lst, self.model)
