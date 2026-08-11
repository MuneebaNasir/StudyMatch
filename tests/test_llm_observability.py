from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from daad_search.query_understanding.llm import ModelNameCapture


def test_model_name_capture_extracts_model_name_from_response_metadata():
    capture = ModelNameCapture()
    message = AIMessage(content="", response_metadata={"model_name": "llama-3.3-70b-versatile"})
    result = LLMResult(generations=[[ChatGeneration(message=message)]])

    capture.on_llm_end(result)

    assert capture.model_name == "llama-3.3-70b-versatile"


def test_model_name_capture_stays_none_when_generations_are_empty():
    capture = ModelNameCapture()
    result = LLMResult(generations=[])

    capture.on_llm_end(result)

    assert capture.model_name is None
