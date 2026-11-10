"""Builds test PDFs with realistic layouts (all text is invented for tests)."""
import pymupdf

FL_ABSTRACT = ("Machine learning on medical data promises better diagnosis, but patient records are scattered across "
               "hospitals that cannot freely share them. Federated learning trains a shared model by exchanging model "
               "updates instead of raw records. In this perspective we describe how the approach could change digital "
               "health, which technical obstacles stand in the way, and why governance matters as much as algorithms.")
FL_INTRO = ("Hospitals hold sensitive records that are difficult to pool. Collaborative training without pooling is "
            "therefore attractive for clinical research. " * 6)
FL_BODY = ("Data from different institutions often follows different distributions because scanners, protocols and "
           "patient populations differ. This heterogeneity remains challenging for current aggregation methods. " * 7)
FL_FUTURE = ("Future work should evaluate aggregation strategies on realistic multi-hospital benchmarks. "
             "Further research is needed on explainability for federated clinical models. " * 2)


class _Page:
    def __init__(self, page): self.page = page
    def insert_textbox(self, *a, **k):
        rc = self.page.insert_textbox(*a, **k)
        assert rc >= 0, f"test PDF text did not fit: {str(a[1])[:30]}"
        return rc


def two_column_no_abstract_heading() -> bytes:
    """Nature-style review: no 'Abstract' heading, bold abstract paragraph, upper-case headings, two columns."""
    doc = pymupdf.open()
    pg = _Page(doc.new_page(width=595, height=842))
    W = 595
    pg.insert_textbox(pymupdf.Rect(40, 30, W - 40, 100), "Federated learning for digital health: a synthetic perspective",
                      fontsize=18, fontname="hebo")
    pg.insert_textbox(pymupdf.Rect(40, 105, W - 40, 125), "Avery Testwell, Jordan Samplewood", fontsize=11, fontname="helv")
    pg.insert_textbox(pymupdf.Rect(40, 128, W - 40, 160),
                      "1 Department of Demonstration, Example University, Springfield, USA. Received: 1 May 2020; "
                      "Accepted: 2 June 2020; Published online: 14 September 2020. e-mail: demo@example.edu",
                      fontsize=8, fontname="helv")
    pg.insert_textbox(pymupdf.Rect(40, 170, W - 40, 330), FL_ABSTRACT, fontsize=10, fontname="hebo")
    col_l, col_r = pymupdf.Rect(40, 350, 285, 800), pymupdf.Rect(310, 350, W - 40, 800)
    pg.insert_textbox(pymupdf.Rect(40, 335, 285, 358), "INTRODUCTION", fontsize=10, fontname="hebo")
    pg.insert_textbox(pymupdf.Rect(40, 362, 285, 800), FL_INTRO[:900], fontsize=9, fontname="helv")
    pg.insert_textbox(pymupdf.Rect(310, 335, W - 40, 358), "CHALLENGES", fontsize=10, fontname="hebo")
    pg.insert_textbox(pymupdf.Rect(310, 360, W - 40, 800), FL_BODY[:900], fontsize=9, fontname="helv")
    pg.insert_textbox(pymupdf.Rect(40, 815, 120, 830), "1", fontsize=8, fontname="helv")
    p2 = _Page(doc.new_page(width=595, height=842))
    p2.insert_textbox(pymupdf.Rect(40, 30, 285, 54), "DISCUSSION", fontsize=10, fontname="hebo")
    p2.insert_textbox(pymupdf.Rect(40, 62, 285, 400), FL_FUTURE, fontsize=9, fontname="helv")
    p2.insert_textbox(pymupdf.Rect(310, 30, W - 40, 54), "REFERENCES", fontsize=10, fontname="hebo")
    p2.insert_textbox(pymupdf.Rect(310, 62, W - 40, 400),
                      "1. Example, A. A study of something else entirely. J. Demo 12, 1-10 (2018).\n"
                      "2. Sample, B. Another reference about unrelated matters. Proc. Demo 3, 44-50 (2019).", fontsize=9, fontname="helv")
    data = doc.tobytes(); doc.close(); return data


def conventional_structured() -> bytes:
    """Single column, 'Abstract' heading with Background/Methods/Results/Conclusions sub-labels."""
    doc = pymupdf.open()
    pg = doc.new_page(width=595, height=842)
    pg.insert_textbox(pymupdf.Rect(60, 50, 535, 90), "A Conventional Study of Something Measurable", fontsize=18, fontname="hebo")
    y = 110
    blocks = [("Abstract", True), ("Background", True),
              ("Models are hard to compare fairly across sites, which motivated this study of evaluation practice.", False),
              ("Methods", True), ("We trained three classifiers on a public dataset and compared their accuracy carefully.", False),
              ("Results", True), ("The second classifier reached the best accuracy in every setting that we tested here.", False),
              ("1. Introduction", True), ("Comparison of models is important. " * 12, False),
              ("2. Methods", True), ("We propose a simple pipeline and evaluate it. " * 10, False),
              ("3. Results", True), ("Our results show clear gains on all datasets. " * 10, False),
              ("4. Limitations", True), ("The study is limited by the small size of the datasets used. " * 3, False),
              ("5. Conclusion", True), ("Careful comparison matters for reproducible progress. " * 4, False),
              ("References", True), ("[1] Example, A. Some reference title. Journal, 2019.", False)]
    for text, bold in blocks:
        h = 18 if bold else 16 * (2 + len(text) // 80)
        rc = pg.insert_textbox(pymupdf.Rect(60, y, 535, y + h), text, fontsize=10, fontname="hebo" if bold else "helv")
        assert rc >= 0, f"test PDF text did not fit: {text[:30]}"
        y += h + 4
        if y > 780:
            pg = doc.new_page(width=595, height=842); y = 50
    data = doc.tobytes(); doc.close(); return data
