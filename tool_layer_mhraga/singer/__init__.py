"""The singer layer: turns an mhRaaga song into a request for YuE2, an open model that SINGS the words.

mhRaaga makes the raga, tala, melody and words. YuE2 supplies a human-sounding vocal and a band. The layer connects them:
  score_to_abc()    the raga melody of a song, written as an ABC score, so the singer follows OUR raga instead of inventing a tune
  build_request()   style words + lyrics + that score -> a YuE2 request
  run_batch.py      runs requests on a GPU machine with the model loaded once (the slow part), and writes MP3s
"""
from .abc import score_to_abc          # noqa: F401
from .request import build_request     # noqa: F401
