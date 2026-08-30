# This one talks directly with the Command Line Interface

from typing import Annotated
from fastapi import FastAPI, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from schemas.incoming_models import FinalAssignments, CountryAndCommitteeList, CountryAndCommittee
app = FastAPI()

@app.post("/hashes")
def add_new_school_or_delegates_and_return_new_hashes(finalassignments: FinalAssignments.finalassignments, bearer_token: Annotated[str | None, HTTPBearer(auto_error=False)] = None):
    """
    This endpoint is used to add new schools or delegates and return new hashes. It requires a valid bearer token for authentication.
    If the bearer token is not provided or is invalid, it will return an HTTP 401 Unauthorized error.
    """
    if bearer_token is None:
        raise HTTPException(status_code=401, detail="Unauthorized: Bearer token missing")
    
    return {"message": "New schools or delegates added successfully", "data": {"schoolName - #1": "hash123abc", "schoolName - #2": "hash456def"}}

@app.post("/hashes/regenerate/delegate")
def regenerate_hash_for_delegate(delegate: Annotated[CountryAndCommittee, Query()], bearer_token: Annotated[str | None, HTTPBearer(auto_error=False)] = None):
    """
    This endpoint is used to regenerate a hash for a delegate. It requires a valid bearer token for authentication.
    If the bearer token is not provided or is invalid, it will return an HTTP 401 Unauthorized error.
    """
    if bearer_token is None:
        raise HTTPException(status_code=401, detail="Unauthorized: Bearer token missing")
    
    return {"message": "Hash regenerated successfully", "data": "hash789ghi"}

@app.post("/hashes/regenerate/school")
def regenerate_hash_for_school(school: Annotated[str, Query()], bearer_token: Annotated[str | None, HTTPBearer(auto_error=False)] = None):
    """
    This endpoint is used to regenerate a hash for a school. It requires a valid bearer token for authentication.
    If the bearer token is not provided or is invalid, it will return an HTTP 401 Unauthorized error.
    """
    if bearer_token is None:
        raise HTTPException(status_code=401, detail="Unauthorized: Bearer token missing")

    return {"message": "Hash regenerated successfully", "data": {"country (committee)": "hash012jkl", "country2 (committee2)": "hash345mno"}}

@app.delete("/hashes")
def drop_delegates_from_school_and_delete_hashes(delegates_to_drop: CountryAndCommitteeList.country_and_committee_list, bearer_token: Annotated[str | None, HTTPBearer(auto_error=False)] = None):
    """
    This endpoint is used to drop delegates from a school and delete their hashes. It requires a valid bearer token for authentication.
    If the bearer token is not provided or is invalid, it will return an HTTP 401 Unauthorized error.
    """
    if bearer_token is None:
        raise HTTPException(status_code=401, detail="Unauthorized: Bearer token missing")
    
    return {"message": "Delegates dropped and hashes deleted successfully", "data": {"school - #1":"hash123abc", "school - #2": "hash456def"}}

@app.get("/hashes")
def return_hashes_for_school(bearer_token: Annotated[str | None, HTTPBearer(auto_error=False)] = None, school_name: str | None = None):
    """
    This endpoint is used to return hashes for a school. It requires a valid bearer token for authentication.
    If the bearer token is not provided or is invalid, it will return an HTTP 401 Unauthorized error.
    """
    if bearer_token is None:
        raise HTTPException(status_code=401, detail="Unauthorized: Bearer token missing")
    
    return {"message": "Hashes retrieved successfully", "data": {"schoolName - #1": "hash123abc", "schoolName - #2": "hash456def"}}

@app.get("/awards")
def return_awards_data(bearer_token: Annotated[str | None, HTTPBearer(auto_error=False)] = None):
    """
    This endpoint is used to return awards data. It requires a valid bearer token for authentication.
    If the bearer token is not provided or is invalid, it will return an HTTP 401 Unauthorized error.
    """
    if bearer_token is None:
        raise HTTPException(status_code=401, detail="Unauthorized: Bearer token missing")
    
    return {"message": "Awards data retrieved successfully", "data": {"CommitteeName": [("CountryName", "AwardName"), ], }}

