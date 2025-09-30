"""Static datasets and presets used by the dashboard."""

INITIAL_COMPANIES = [
    {"name": "Pfizer", "n_I": 45, "n_II": 28, "n_III": 37},
    {"name": "BIOCAD", "n_I": 15, "n_II": 9, "n_III": 18},
    {"name": "Generium", "n_I": 7, "n_II": 6, "n_III": 9},
    {"name": "R-Pharm", "n_I": 11, "n_II": 8, "n_III": 12},
    {"name": "Pharmstandard", "n_I": 9, "n_II": 7, "n_III": 10},
    {"name": "Geropharm", "n_I": 5, "n_II": 4, "n_III": 6},
    {"name": "Petrovax", "n_I": 6, "n_II": 5, "n_III": 7},
    {"name": "Valenta", "n_I": 5, "n_II": 4, "n_III": 6},
    {"name": "Nanolek", "n_I": 6, "n_II": 5, "n_III": 6},
    {"name": "ChemRar", "n_I": 7, "n_II": 6, "n_III": 5},
]

INITIAL_PARAMETERS = {
    "p1": 0.47,
    "p2": 0.28,
    "p3": 0.55,
    "C_I": 25,
    "C_II": 60,
    "C_III": 350,
    "C_REG": 3,
    "coop_c3_reduction": 20,
    "coop_dp3": 0.05,
    "coop_p3_cap": 0.70,
}

PARAMETER_PRESETS = {
    "avg": INITIAL_PARAMETERS.copy(),
    "ru": {
        "p1": 0.47,
        "p2": 0.30,
        "p3": 0.58,
        "C_I": 20,
        "C_II": 50,
        "C_III": 230,
        "C_REG": 2,
        "coop_c3_reduction": 30,
        "coop_dp3": 0.06,
        "coop_p3_cap": 0.80,
    },
}
