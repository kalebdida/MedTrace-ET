"""A model module whose load() fails, as a missing weights file would."""


def load():
    raise FileNotFoundError("weights.onnx")
