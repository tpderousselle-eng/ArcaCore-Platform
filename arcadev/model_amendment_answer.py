"""Explicit user declarations, never adapter acceptance or inferred field names."""
from dataclasses import dataclass
from enum import Enum

from .architecture_specification import Record, _parse, _text
from .model_amendment_request import (
    ModelAmendmentFieldProposal, checked, exact_result, identified, inert,
)

ARCADEV_MODEL_AMENDMENT_ANSWER_SCHEMA = "arcadev.model_amendment_answer"
ARCADEV_MODEL_AMENDMENT_ANSWER_SCHEMA_VERSION = 1


class ModelAmendmentResolutionAction(str, Enum):
    ACCEPT = "accept"


@dataclass(frozen=True)
class ModelAmendmentAnswer(Record):
    answer_id: str
    request_id: str
    parent_approval_id: str
    target_finalization_id: str
    question_id: str
    entity_id: str
    user_answer: str
    declaration_quote: str
    field: ModelAmendmentFieldProposal
    action: ModelAmendmentResolutionAction
    provenance: str = "explicit_user"
    schema: str = ARCADEV_MODEL_AMENDMENT_ANSWER_SCHEMA
    schema_version: int = 1

    @classmethod
    def create(cls, *, request_id, parent_approval_id, target_finalization_id, question_id,
               entity_id, user_answer, declaration_quote, field, action):
        values = [_text(v, maximum=240) for v in
            (request_id, parent_approval_id, target_finalization_id, question_id, entity_id)]
        user_answer = _text(user_answer, "Explicit amendment answer", 20_000, preserve=True)
        quote = _text(declaration_quote, "Complete declaration quote", 16_000, preserve=True)
        if quote not in user_answer:
            raise ValueError("Evidence must be quoted unchanged from the explicit user answer.")
        raw = field.canonical_dict() if type(field) is ModelAmendmentFieldProposal else field
        field = ModelAmendmentFieldProposal.from_dict(raw)
        quoted = ModelAmendmentFieldProposal.from_dict(_parse(quote))
        if quoted != field or field.entity_id != entity_id:
            raise ValueError("Quoted complete declaration must match every normalized field value and target.")
        result = cls("", *values, user_answer, quote, field, ModelAmendmentResolutionAction(action))
        result = identified(result, "answer_id", "model_amendment_answer")
        inert(result.canonical_dict())
        return result

    @classmethod
    def from_dict(cls, value):
        checked(value, cls, ARCADEV_MODEL_AMENDMENT_ANSWER_SCHEMA)
        args = {k: v for k, v in value.items() if k not in {"answer_id", "provenance", "schema", "schema_version"}}
        return exact_result(cls.create(**args), value)

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(_parse(text))
