import io

from PIL import Image

from daad_search.transcript import local_vlm as local_vlm_module


def _fake_png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (1, 1)).save(buffer, format="PNG")
    return buffer.getvalue()


class _FakeModel:
    def __init__(self, answer: str):
        self._answer = answer

    def encode_image(self, image):
        return image

    def answer_question(self, encoded_image, question, tokenizer):
        return self._answer


def test_extract_with_local_vlm_parses_json_response(monkeypatch):
    answer = (
        '{"courses": [{"name": "Linear Algebra", "grade": "A"}], '
        '"grade_value": 3.8, "grade_scale": "4.0 GPA", "nationality": "Pakistan", '
        '"degree_field": "Computer Science"}'
    )
    monkeypatch.setattr(local_vlm_module, "_load_model", lambda: (_FakeModel(answer), object()))

    result = local_vlm_module.extract_with_local_vlm([_fake_png_bytes()])

    assert result.extraction_confidence == "medium"
    assert result.courses[0].name == "Linear Algebra"
    assert result.grade_value == 3.8
    assert result.nationality == "Pakistan"


def test_extract_with_local_vlm_falls_back_to_low_confidence_on_unparseable_output(monkeypatch):
    monkeypatch.setattr(local_vlm_module, "_load_model", lambda: (_FakeModel("not json"), object()))

    result = local_vlm_module.extract_with_local_vlm([_fake_png_bytes()])

    assert result.extraction_confidence == "low"
    assert result.courses == []
