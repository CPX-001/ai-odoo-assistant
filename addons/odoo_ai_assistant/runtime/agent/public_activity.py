"""Dependency-light closed contracts for Phase 3 public Assistant activity.

Production persistence integration remains blocked until the Phase 2 real gates pass.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import TypeAlias
JsonObject: TypeAlias = dict[str, object]
PUBLIC_EVENT_KINDS = frozenset({"turn.queued","turn.started","provider.connecting","provider.connected","agent.answer.started","capability.started","capability.completed","capability.failed","retrieval.started","retrieval.completed","preview.started","preview.completed","approval.required","execution.started","execution.completed","verification.started","verification.completed","turn.completed","turn.failed","turn.cancelled"})
PUBLIC_EVENT_PHASES = frozenset({"queue","provider","answer","capability","retrieval","preview","approval","execution","verification","finalization"})
PUBLIC_EVENT_STATUSES = frozenset({"pending","running","completed","failed","blocked","cancelled"})
_TURN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$")
_MODEL_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_CAPABILITY_RE = _MODEL_RE
_DIAGNOSTIC_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_OCCURRED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")
_MAX_LABEL=240; _MAX_RESOURCE_RECORDS=20; _MAX_DISPLAY_NAME=160
class PublicTurnEventError(RuntimeError):
    def __init__(self, code="public_turn_event_invalid"): super().__init__(code); self.code=code
def _one_line(value, *, maximum):
    if not isinstance(value,str): raise PublicTurnEventError()
    normalized=" ".join(value.split())
    if not 1 <= len(normalized) <= maximum or "\x00" in normalized: raise PublicTurnEventError()
    return normalized
def _resource(value):
    if value is None: return None
    if not isinstance(value,dict) or set(value)!={"model","record_ids","display_names"}: raise PublicTurnEventError()
    model=value.get("model"); ids=value.get("record_ids"); names=value.get("display_names")
    if model is not None and (not isinstance(model,str) or _MODEL_RE.fullmatch(model) is None): raise PublicTurnEventError()
    if not isinstance(ids,list) or len(ids)>_MAX_RESOURCE_RECORDS or any(type(x) is not int or x<=0 for x in ids) or len(set(ids))!=len(ids): raise PublicTurnEventError()
    if not isinstance(names,list) or len(names)>_MAX_RESOURCE_RECORDS or any(not isinstance(x,str) for x in names): raise PublicTurnEventError()
    names=tuple(_one_line(x,maximum=_MAX_DISPLAY_NAME) for x in names)
    if names and len(names)!=len(ids): raise PublicTurnEventError()
    if (ids or names) and model is None: raise PublicTurnEventError()
    return {"model":model,"record_ids":list(ids),"display_names":list(names)}
@dataclass(frozen=True,slots=True)
class PublicTurnEvent:
    sequence:int; turn_id:str; kind:str; phase:str; status:str; label:str; resource:JsonObject|None; capability:str|None; progress:int|None; diagnostic_code:str|None; occurred_at:str
    def __post_init__(self):
        if type(self.sequence) is not int or self.sequence<=0: raise PublicTurnEventError()
        if not isinstance(self.turn_id,str) or _TURN_ID_RE.fullmatch(self.turn_id) is None: raise PublicTurnEventError()
        if self.kind not in PUBLIC_EVENT_KINDS or self.kind=="agent.thinking": raise PublicTurnEventError()
        if self.phase not in PUBLIC_EVENT_PHASES or self.status not in PUBLIC_EVENT_STATUSES: raise PublicTurnEventError()
        object.__setattr__(self,"label",_one_line(self.label,maximum=_MAX_LABEL)); object.__setattr__(self,"resource",_resource(self.resource))
        if self.capability is not None and (not isinstance(self.capability,str) or _CAPABILITY_RE.fullmatch(self.capability) is None): raise PublicTurnEventError()
        if self.progress is not None and (type(self.progress) is not int or not 0<=self.progress<=100): raise PublicTurnEventError()
        if self.diagnostic_code is not None and (not isinstance(self.diagnostic_code,str) or _DIAGNOSTIC_RE.fullmatch(self.diagnostic_code) is None): raise PublicTurnEventError()
        if not isinstance(self.occurred_at,str) or _OCCURRED_AT_RE.fullmatch(self.occurred_at) is None: raise PublicTurnEventError()
@dataclass(frozen=True,slots=True)
class PublicCapabilityActivityDescriptor:
    started_label:str; completed_label:str; failed_label:str
    def __post_init__(self):
        object.__setattr__(self,"started_label",_one_line(self.started_label,maximum=_MAX_LABEL)); object.__setattr__(self,"completed_label",_one_line(self.completed_label,maximum=_MAX_LABEL)); object.__setattr__(self,"failed_label",_one_line(self.failed_label,maximum=_MAX_LABEL))
def parse_public_turn_event(value):
    keys={"sequence","turn_id","kind","phase","status","label","resource","capability","progress","diagnostic_code","occurred_at"}
    if not isinstance(value,dict) or set(value)!=keys: raise PublicTurnEventError()
    try: return PublicTurnEvent(**value)
    except (KeyError,TypeError): raise PublicTurnEventError() from None
def public_turn_event_payload(event):
    if not isinstance(event,PublicTurnEvent): raise PublicTurnEventError()
    resource=None if event.resource is None else {"model":event.resource["model"],"record_ids":list(event.resource["record_ids"]),"display_names":list(event.resource["display_names"])}
    return {"sequence":event.sequence,"turn_id":event.turn_id,"kind":event.kind,"phase":event.phase,"status":event.status,"label":event.label,"resource":resource,"capability":event.capability,"progress":event.progress,"diagnostic_code":event.diagnostic_code,"occurred_at":event.occurred_at}
def validate_event_batch(value, *, after_sequence=0, maximum=100):
    if type(after_sequence) is not int or after_sequence<0 or not 1<=maximum<=100 or not isinstance(value,list) or len(value)>maximum: raise PublicTurnEventError()
    events=tuple(parse_public_turn_event(x) for x in value); previous=after_sequence; turn_id=None
    for event in events:
        if event.sequence<=previous: raise PublicTurnEventError("public_turn_event_order_invalid")
        if turn_id is None: turn_id=event.turn_id
        elif event.turn_id!=turn_id: raise PublicTurnEventError("public_turn_event_turn_mismatch")
        previous=event.sequence
    return events
