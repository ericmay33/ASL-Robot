FINGERSPELL_CACHE = {
    "A": None,
    "B": None,
    "C": {
  "token": "C",
  "type": "STATIC",
  "duration": 2.0,
  "keyframes": [
    {
      "time": 0.0,
      "R": [
        0,
        110,
        110,
        110,
        110
      ]
    }
  ]
}
,
    "D": {
  "token": "D",
  "type": "STATIC",
  "duration": 2.0,
  "keyframes": [
    {
      "time": 0.0,
      "R": [
        0,
        50,
        130,
        130,
        130
      ]
    }
  ]
}
,
    "E": {
  "token": "E",
  "type": "STATIC",
  "duration": 2.0,
  "keyframes": [
    {
      "time": 0.0,
      "R": [
        0,
        155,
        155,
        155,
        155
      ]
    }
  ]
}
,
    "F": None,
    "G": None,
    "H": None,
    "I": None,
    "J": None,
    "K": None,
    "L": None,
    "M": None,
    "N": None,
    "O": {
  "token": "O",
  "type": "STATIC",
  "duration": 2.0,
  "keyframes": [
    {
      "time": 0.0,
      "R": [
        0,
        140,
        140,
        140,
        140
      ]
    }
  ]
}
,
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