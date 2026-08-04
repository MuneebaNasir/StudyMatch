from bs4 import BeautifulSoup

_LABEL_TO_KEY = {
    "Description/content": "description",
    "Academic admission requirements": "admission_requirements",
    "German language skills": "german_language",
    "English language skills": "english_language",
    "Tuition fees per semester": "tuition_fees",
    "Application periods": "application_deadline",
    "Degree": "degree",
}


def parse_detail_sections(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    sections: dict[str, str] = {}

    for dt in soup.select("dt.c-description-list__content"):
        label = dt.get_text(strip=True)
        key = _LABEL_TO_KEY.get(label)
        if key is None:
            continue

        dd = dt.find_next_sibling("dd")
        if dd is None:
            continue

        sections[key] = dd.get_text(separator="\n", strip=True)

    return sections
