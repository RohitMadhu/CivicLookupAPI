from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class NormalizedInput(BaseModel):
    line1: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""

class Official(BaseModel):
    name: str
    party: Optional[str] = None
    emails: Optional[List[str]] = None
    phones: Optional[List[str]] = None
    urls: Optional[List[str]] = None
    photoUrl: Optional[str] = None
    channels: Optional[List[Dict[str, str]]] = None
    address: Optional[List[Dict[str, str]]] = None

class Office(BaseModel):
    name: str
    divisionId: str
    levels: List[str]
    roles: Optional[List[str]] = None
    officialIndices: List[int]

class RepresentativeInfoResponse(BaseModel):
    kind: str = "civicinfo#representativeInfoResponse"
    normalizedInput: NormalizedInput
    divisions: Dict[str, Dict[str, Any]]
    offices: Optional[List[Office]] = None
    officials: Optional[List[Official]] = None

class DivisionsByAddressResponse(BaseModel):
    kind: str = "civicinfo#divisionsByAddressResponse"
    normalizedInput: NormalizedInput
    divisions: Dict[str, Dict[str, Any]]