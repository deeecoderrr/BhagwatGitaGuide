"""Income-tax e-filing state codes (Address.StateCode) → display name."""
from __future__ import annotations

# Common 2-digit codes used in ITR JSON (extend as needed).
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
    "26": "Dadra & Nagar Haveli",
    "27": "Maharashtra",
    "28": "Andhra Pradesh (before division)",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Uttar Pradesh",
    "32": "Lakshadweep",
    "33": "Kerala",
    "34": "Tamil Nadu",
    "35": "Puducherry",
    "36": "Andaman & Nicobar Islands",
    "37": "Telangana",
    "38": "Andhra Pradesh",
    "97": "Other Territory",
    "99": "Outside India / Foreign",
}


def state_name_from_code(code: str | int | None) -> str:
    """Return state name for ITR state code, or empty string if unknown."""
    if code is None:
        return ""
    s = str(code).strip()
    if not s:
        return ""
    if len(s) == 1:
        s = s.zfill(2)
    return STATE_CODE_TO_NAME.get(s, "")
