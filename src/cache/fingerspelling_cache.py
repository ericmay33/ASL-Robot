FINGERSPELL_CACHE = {
    "A": None,
    "B": None,
    "C": None,
    "D": None,
    "E": None,
    "F": None,
    "G": None,
    "H": None,
    "I": None,
    "J": None,
    "K": None,
    "L": None,
    "M": None,
    "N": None,
    "O": None,
    "P": None,
    "Q": None,
    "R": None,
    "S": None,
    "T": None,
    "U": None,
    "V": None,
    "W": None,
    "X": None,
    "Y": None,
    "Z": None,
}

# Returns JSON for letter motion from cache
def get_letter_motion(letter: str):
    return FINGERSPELL_CACHE.get(letter.upper())