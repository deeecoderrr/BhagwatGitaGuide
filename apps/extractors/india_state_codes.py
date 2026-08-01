"""Income-tax e-filing state codes (Address.StateCode) → display name."""
from __future__ import annotations

import re

# Current ITR / e-filing master (GST-aligned numbering used in filed JSON).
STATE_CODE_TO_NAME: dict[str, str] = {
    "01": "Jammu & Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "25": "Daman & Diu",
    "26": "Dadra & Nagar Haveli and Daman & Diu",
    "27": "Maharashtra",
    "28": "Andhra Pradesh",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman & Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
    "97": "Other Territory",
    "99": "Centre Jurisdiction / Foreign",
}

# Postal / India Post state names → ITR StateCode (uppercase keys).
POSTAL_STATE_NAME_TO_CODE: dict[str, str] = {
    "ANDAMAN AND NICOBAR ISLANDS": "35",
    "ANDHRA PRADESH": "37",
    "ARUNACHAL PRADESH": "12",
    "ASSAM": "18",
    "BIHAR": "10",
    "CHANDIGARH": "04",
    "CHHATTISGARH": "22",
    "DADRA AND NAGAR HAVELI": "26",
    "DADRA AND NAGAR HAVELI AND DAMAN AND DIU": "26",
    "DADRA & NAGAR HAVELI AND DAMAN AND DIU": "26",
    "DAMAN AND DIU": "26",
    "DELHI": "07",
    "GOA": "30",
    "GUJARAT": "24",
    "HARYANA": "06",
    "HIMACHAL PRADESH": "02",
    "JAMMU AND KASHMIR": "01",
    "JAMMU & KASHMIR": "01",
    "JHARKHAND": "20",
    "KARNATAKA": "29",
    "KERALA": "32",
    "LADAKH": "38",
    "LAKSHADWEEP": "31",
    "MADHYA PRADESH": "23",
    "MAHARASHTRA": "27",
    "MANIPUR": "14",
    "MEGHALAYA": "17",
    "MIZORAM": "15",
    "NAGALAND": "13",
    "ODISHA": "21",
    "ORISSA": "21",
    "PONDICHERRY": "34",
    "PUDUCHERRY": "34",
    "PUNJAB": "03",
    "RAJASTHAN": "08",
    "SIKKIM": "11",
    "TAMIL NADU": "33",
    "TELANGANA": "36",
    "TRIPURA": "16",
    "UTTAR PRADESH": "09",
    "UTTARAKHAND": "05",
    "WEST BENGAL": "19",
}

_SPACE_RE = re.compile(r"\s+")


def normalize_postal_state_name(name: str) -> str:
    cleaned = (name or "").strip().upper().replace("&", "AND")
    return _SPACE_RE.sub(" ", cleaned)


def state_name_from_code(code: str | int | None) -> str:
    """Return state name for ITR state code, or empty string if unknown."""
    normalized = normalize_state_code(code)
    if not normalized:
        return ""
    return STATE_CODE_TO_NAME.get(normalized, "")


def normalize_state_code(code: str | int | None) -> str:
    if code is None:
        return ""
    s = str(code).strip()
    if not s:
        return ""
    if len(s) == 1:
        s = s.zfill(2)
    return s


def state_code_from_postal_name(name: str | None) -> str:
    """Map India Post state name to ITR StateCode."""
    key = normalize_postal_state_name(name or "")
    if not key:
        return ""
    return POSTAL_STATE_NAME_TO_CODE.get(key, "")
