import pathlib
import re

import html2text

from . import embeddings

h = html2text.HTML2Text(bodywidth=0)

# with open("common_en.txt") as f:
#     common_words = list([i.strip() for i in f.read().split("\n") if i.strip()])


class Document:
    def __init__(self, title, text):
        self.title = title
        self.text = text

        self.title_embedding = None


# m = embeddings.EmbeddingsModel(slow=False)
# lu = m.get_lookup(list([(i, i) for i in common_words]), retrieval=False)


# def similar_words(w, n):
#     x = lu.match(w)
#     return list([i[1] for i in x[-n:] if i[0] > 0.18])


# def remove_common(s: list[str]) -> list[str]:
#     c = common_words[:256]
#     s = list(s)
#     for i in c:
#         if i in s:
#             s.remove(i)
#     return s


# def get_related_terms(qr: str, n: int) -> list[str]:
#     return similar_words(qr, n)


# def common_subsequences(a, b):
#     op = []
#     for i in range(5):
#         res = pylcs.lcs_string_idx(a, b)
#         x = "".join([b[i] for i in res if i != -1])
#         if len(x) > 3:
#             op.append(x)
#             a = a.replace(x, "")
#             b = b.replace(x, "")

#     x = 1
#     for i in op:
#         x *= len(i)

#     return x


def chunkstring(string, length):
    return (string[0 + i : length + i] for i in range(0, len(string), length))


def strip_md(i: str) -> str:
    # images
    i = re.sub(r"!\[(.+?)\]\(.+?\)", r"\1", i)
    i = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", i)
    i = re.sub(r"_(\w)+?_", r"\1", i)
    # citattions
    i = re.sub(r"([\.\] ])\[\d+\]", r"\1", i)
    return i


def summarize2(
    d: str, title: str, query: str, m: embeddings.EmbeddingsModel
) -> list[tuple[float, str, str]]:
    query = query.lower()
    d = d.lower()
    d = strip_md(d)

    # d = list(chunkstring(orig, 96))

    paragraphs = re.split("\n\n", d)

    lower_title = title.lower()

    paragraphs_with_similarity: list[tuple[float, str, str]] = []

    section_title = ""

    for p in paragraphs:
        peak = 0
        sum = 0
        sentences: list[str] = []

        if len(p) > 1200:
            continue

        x = re.split(r"\n|(\. )", p)

        for j in x:
            if j:
                j = j.strip()
                if j.startswith("#"):
                    section_title = j.replace("#", "").strip()
                    continue

                if len(j.lower().replace(lower_title, "")) > 5:
                    sentences.append(f"{lower_title}: {section_title}: {j}")

        if sentences:
            lu = m.get_lookup([(i, i) for i in sentences], retrieval=True)

            sm = lu.match(query)
            for i in sm:
                peak = max(peak, i[0])
                sum += i[0]
            lu2 = m.get_lookup(
                [(f"{lower_title}: {section_title}: {p}", None)], retrieval=True
            )
            sm2 = lu2.match(query)[0][0]

            paragraphs_with_similarity.append((max(peak, sm2), title, p))

    paragraphs_with_similarity.sort(reverse=True)

    return paragraphs_with_similarity[:6]


def rerank(
    docs: list[tuple[float, str, str]], q: str, m: embeddings.EmbeddingsModel
) -> list[tuple[float, str, str]]:
    lu = m.get_lookup([(i[1], i[2]) for i in docs], retrieval=True)

    sim = lu.match(q)

    return sim


def stringify_query(terms, qr):
    return " OR ".join(list([f'"{i}"' for i in terms])) + ' OR "' + qr + '"'


def narrow_docs(
    docs: list[tuple[str, str]], query: str, m: embeddings.EmbeddingsModel
) -> list[tuple[float, str, str]]:
    "Input is title, article"

    docs = list(set(docs))

    lu = m.get_lookup(docs, retrieval=True)

    x = lu.match(query)

    lu2 = m.get_lookup(
        [(i[0] + ": " + (i[1][:256] or i[0]), None) for i in docs],
        retrieval=True,
    )

    # Look at the start of the docs to get a better idea of the subject
    x2 = lu2.match(query)

    x = list(
        [(max(x[i][0], x2[i][0]), x[i][1], x[i][2]) for i in range(len(x))]
    )

    x.sort()
    x.reverse()

    return x


def search_documents(
    docs: list[tuple[float, str, str]],
    qr: str,
    fast_embed: embeddings.EmbeddingsModel,
    hq_embed: embeddings.EmbeddingsModel,
) -> list[tuple[float, str, str]]:
    """Given documents, return ranked passages"""
    sums: list[tuple[float, str, str]] = []
    for i in docs:
        sums.extend(summarize2(i[2], i[1], qr, fast_embed))

    sums.sort()
    sums.reverse()
    sums = sums[:6]

    sums = rerank(sums, qr, hq_embed)

    # sums = list([(i[0], i[1], i[2]) for i in sums if i[0] > 0.28])

    return sums


class ZimKnowledgeBase:
    def __init__(self, fn: str):
        from libzim.reader import Archive

        self.zim = Archive(pathlib.Path(fn))

    def batch_get_wiki(self, lst: list[str]) -> list[tuple[str, str]]:
        top = [self.zim.get_entry_by_path(i) for i in lst]

        o = []
        for i in top:
            html = bytes(i.get_item().content).decode("UTF-8")
            md = h.handle(html)
            md = md.split("## References")[0]
            md = md.split("## Notes")[0]
            md = md.split("## External Links")[0]

            o.append((i.title, md))
        return list(o)

    def collect_wiki_titles(
        self, search_query: str, number: int
    ) -> list[tuple[str, str]]:
        from libzim.search import Query, Searcher

        # searching using full-text index
        search_string = search_query
        query = Query().set_query(search_string)
        searcher = Searcher(self.zim)
        search = searcher.search(query)
        search_count = search.getEstimatedMatches()
        top = (list(search.getResults(0, search_count)))[:number]

        top = [(self.zim.get_entry_by_path(i).title, i) for i in top]

        return top

    def search(
        self, q: str, m: embeddings.EmbeddingsModel
    ) -> list[tuple[str, str]]:
        # terms= get_related_terms(q, 10)
        # Full query comes first, those get priority
        articles = self.collect_wiki_titles(q, 10)

        for i in q.split(". "):
            a = self.collect_wiki_titles(i, 10)
            for j in a:
                if j not in articles:
                    articles.append(j)

        # Long words prob more interesting
        for i in sorted(q.split(" "), key=len, reverse=True):
            a = self.collect_wiki_titles(i, 3)
            for j in a:
                if j not in articles:
                    articles.append(j)

            # similar = similar_words(i, 4)
            # for j in similar:
            #     if j.lower() in q:
            #         continue
            #     # print(i, j)
            #     a = self.collect_wiki_titles(q.replace(i, j), 3)
            #     for j in a:
            #         if j not in articles:
            #             articles.append(j)

        articles = articles[:30]

        # use just the titles and file paths to find the 10 best
        narrowed = narrow_docs(articles, q, m)[:15]

        docs = self.batch_get_wiki(list([i[2] for i in narrowed]))

        return docs
