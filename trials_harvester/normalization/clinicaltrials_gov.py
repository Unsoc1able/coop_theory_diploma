"""Normalisation helpers for ClinicalTrials.gov studies."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional

from .models import Trial
from .utils import (
    normalize_countries,
    normalize_phase,
    normalize_status,
    normalize_study_type,
    parse_date,
)

_EUDRACT_RE = re.compile(r"\d{4}-\d{6}-\d{2}")
_ISRCTN_RE = re.compile(r"ISRCTN\d+")


def _as_list(value: object) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [value]
    return []


def _extract_secondary_ids(module: Dict[str, object]) -> List[str]:
    secondary = module.get("SecondaryIdList")
    if isinstance(secondary, dict):
        return [str(item) for item in _as_list(secondary.get("SecondaryId"))]
    return []


def _extract_locations(module: Dict[str, object]) -> List[Dict[str, object]]:
    location_list = module.get("LocationList")
    if isinstance(location_list, dict):
        locations = location_list.get("Location")
        if isinstance(locations, list):
            return [loc for loc in locations if isinstance(loc, dict)]
    return []


def _extract_interventions(module: Dict[str, object]) -> List[str]:
    result: List[str] = []
    intervention_list = module.get("InterventionList")
    if isinstance(intervention_list, dict):
        interventions = intervention_list.get("Intervention")
        if isinstance(interventions, list):
            for item in interventions:
                if isinstance(item, dict):
                    name = item.get("InterventionName") or item.get("Name")
                    if isinstance(name, str) and name.strip():
                        result.append(name.strip())
    return result


def _extract_conditions(module: Dict[str, object]) -> List[str]:
    condition_list = module.get("ConditionList")
    if isinstance(condition_list, dict):
        return [
            cond.strip()
            for cond in _as_list(condition_list.get("Condition"))
            if isinstance(cond, str) and cond.strip()
        ]
    return []


def _unique(values: Iterable[str]) -> List[str]:
    result: List[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def normalize_study(study: Dict[str, object]) -> Trial:
    protocol = study.get("ProtocolSection", {}) if isinstance(study, dict) else {}
    if not isinstance(protocol, dict):
        protocol = {}

    id_module = protocol.get("IdentificationModule", {})
    status_module = protocol.get("StatusModule", {})
    design_module = protocol.get("DesignModule", {})
    sponsor_module = protocol.get("SponsorCollaboratorsModule", {})
    conditions_module = protocol.get("ConditionsModule", {})
    arms_module = protocol.get("ArmsInterventionsModule", {})
    contacts_module = protocol.get("ContactsLocationsModule", {})
    countries_module = protocol.get("LocationCountriesModule", {})

    id_module = id_module if isinstance(id_module, dict) else {}
    status_module = status_module if isinstance(status_module, dict) else {}
    design_module = design_module if isinstance(design_module, dict) else {}
    sponsor_module = sponsor_module if isinstance(sponsor_module, dict) else {}
    conditions_module = conditions_module if isinstance(conditions_module, dict) else {}
    arms_module = arms_module if isinstance(arms_module, dict) else {}
    contacts_module = contacts_module if isinstance(contacts_module, dict) else {}
    countries_module = countries_module if isinstance(countries_module, dict) else {}

    nct_id = id_module.get("NCTId") if isinstance(id_module.get("NCTId"), str) else None
    org_id = None
    org_info = id_module.get("OrgStudyIdInfo")
    if isinstance(org_info, dict):
        org_id = org_info.get("OrgStudyId") if isinstance(org_info.get("OrgStudyId"), str) else None

    source_id = nct_id or org_id
    if not source_id:
        raise ValueError("ClinicalTrials.gov study is missing a primary identifier")

    secondary_ids = _extract_secondary_ids(id_module)
    eudract_number = next((sid for sid in secondary_ids if _EUDRACT_RE.search(sid)), None)
    isrctn = next((sid for sid in secondary_ids if _ISRCTN_RE.search(sid.upper())), None)

    lead_sponsor = None
    lead_info = sponsor_module.get("LeadSponsor")
    if isinstance(lead_info, dict):
        lead_sponsor = lead_info.get("LeadSponsorName") or lead_info.get("Name")
        if isinstance(lead_sponsor, str):
            lead_sponsor = lead_sponsor.strip()
        else:
            lead_sponsor = None

    collaborators: List[str] = []
    collab_list = sponsor_module.get("CollaboratorList")
    if isinstance(collab_list, dict):
        for entry in collab_list.get("Collaborator", []):
            if isinstance(entry, dict):
                name = entry.get("CollaboratorName") or entry.get("Name")
                if isinstance(name, str) and name.strip():
                    collaborators.append(name.strip())

    sponsors_all = _unique([lead_sponsor or "", *collaborators])
    if sponsors_all and not sponsors_all[0]:
        sponsors_all = sponsors_all[1:]

    enrollment_info = design_module.get("EnrollmentInfo") if isinstance(design_module, dict) else {}
    enrollment = None
    if isinstance(enrollment_info, dict):
        raw_enrollment = enrollment_info.get("EnrollmentCount")
        if isinstance(raw_enrollment, (int, float)):
            enrollment = int(raw_enrollment)
        elif isinstance(raw_enrollment, str):
            try:
                enrollment = int(raw_enrollment.replace(",", ""))
            except ValueError:
                enrollment = None

    phase_list = []
    phase_data = design_module.get("PhaseList")
    if isinstance(phase_data, dict):
        phase_list = _as_list(phase_data.get("Phase"))
    phase = normalize_phase(phase_list)

    overall_status = None
    raw_status = status_module.get("OverallStatus")
    if isinstance(raw_status, str):
        overall_status = normalize_status(raw_status)

    study_type = None
    raw_type = design_module.get("StudyType") or study.get("StudyType")
    if isinstance(raw_type, str):
        study_type = normalize_study_type(raw_type)

    locations = _extract_locations(contacts_module)
    centers_count = len(locations) if locations else None
    location_countries: List[str] = []
    if locations:
        for loc in locations:
            country = loc.get("LocationCountry") if isinstance(loc, dict) else None
            if isinstance(country, str) and country.strip():
                location_countries.append(country.strip())
    country_module_list = countries_module.get("LocationCountry")
    if isinstance(country_module_list, list):
        location_countries.extend(
            [c for c in country_module_list if isinstance(c, str) and c.strip()]
        )

    conditions = _extract_conditions(conditions_module)
    interventions = _extract_interventions(arms_module)

    start_struct = status_module.get("StartDateStruct")
    start_date = None
    if isinstance(start_struct, dict):
        start_date = parse_date(start_struct.get("StartDate"))
    if not start_date:
        start_date = parse_date(status_module.get("StartDate"))

    primary_completion_struct = status_module.get("PrimaryCompletionDateStruct")
    primary_completion_date = None
    if isinstance(primary_completion_struct, dict):
        primary_completion_date = parse_date(
            primary_completion_struct.get("PrimaryCompletionDate")
        )
    if not primary_completion_date:
        primary_completion_date = parse_date(status_module.get("PrimaryCompletionDate"))

    completion_struct = status_module.get("CompletionDateStruct")
    completion_date = None
    if isinstance(completion_struct, dict):
        completion_date = parse_date(completion_struct.get("CompletionDate"))
    if not completion_date:
        completion_date = parse_date(status_module.get("CompletionDate"))

    last_update_struct = status_module.get("LastUpdatePostDateStruct")
    last_updated_date = None
    if isinstance(last_update_struct, dict):
        last_updated_date = parse_date(last_update_struct.get("LastUpdatePostDate"))
    if not last_updated_date:
        last_updated_date = parse_date(status_module.get("LastUpdatePostDate"))

    protocol_id = org_id

    trial = Trial(
        source="clinicaltrials_gov",
        source_id=source_id,
        public_title=id_module.get("BriefTitle") if isinstance(id_module.get("BriefTitle"), str) else None,
        scientific_title=id_module.get("OfficialTitle")
        if isinstance(id_module.get("OfficialTitle"), str)
        else None,
        sponsor_primary=lead_sponsor,
        sponsors_all=sponsors_all,
        phase=phase,
        overall_status=overall_status,
        study_type=study_type,
        enrollment=enrollment,
        centers_count=centers_count,
        countries=normalize_countries(location_countries),
        conditions=conditions,
        interventions=_unique(interventions),
        start_date=start_date,
        primary_completion_date=primary_completion_date,
        completion_date=completion_date,
        nct_id=nct_id,
        eudract_number=eudract_number,
        isrctn=isrctn,
        protocol_id=protocol_id,
        last_updated_date=last_updated_date,
        language="en",
        raw_payload=study,
    )
    return trial


__all__ = ["normalize_study"]
