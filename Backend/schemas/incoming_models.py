from pydantic import BaseModel

class FinalAssignments(BaseModel):
    finalassignments = dict[str, list[str]]
    # format: {"schoolName - #1" : ["committeeName", "CommitteeType", "Country"] ...}

class CountryAndCommitteeList(BaseModel):
    country_and_committee_list = list[str]
    # format: [["Country", "CommitteeName", "CommitteeType"] ...]

class CountryAndCommittee(BaseModel):
    committee: str
    country: str