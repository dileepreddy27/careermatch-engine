from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RawJob(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=20, max_length=30000)
    source: str = Field(default="manual", max_length=2048)


class Requirement(StrictModel):
    skill: str = Field(min_length=1, max_length=80)
    quote: str = Field(min_length=1, max_length=1000)


class Requirements(StrictModel):
    requirements: list[Requirement] = Field(default_factory=list, max_length=50)


class MatchRequest(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    resume: str = Field(min_length=20, max_length=50000)
    jobs: list[RawJob] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_jobs(self):
        if len({j.id for j in self.jobs}) != len(self.jobs):
            raise ValueError("Job IDs must be unique")
        if sum(len(j.text) for j in self.jobs) > 300000:
            raise ValueError("Total job text exceeds 300,000 characters")
        return self


class Chunk(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    id: str
    section: str
    text: str
    start: int
    end: int


class Evidence(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    chunk_id: str
    section: str
    quote: str
    start: int
    end: int


class RequirementMatch(StrictModel):
    skill: str
    job_quote: str
    status: Literal["supported", "gap"]
    evidence: Evidence | None = None


class JobMatch(StrictModel):
    id: str
    title: str
    company: str
    source: str
    rank_score: float
    vector_similarity: float
    coverage: float
    requirements: list[RequirementMatch]
    suggested_excerpts: list[Evidence]
    gaps: list[str]


class MatchResponse(StrictModel):
    mode: str
    extraction: str
    disclaimer: str
    chunks: int
    matches: list[JobMatch]
