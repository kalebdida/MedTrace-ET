"""Test double for the packaging model, loaded through VISUAL_MODEL_MODULE.

The "photo" is a JPEG signature followed by an instruction, e.g.
b"\xff\xd8\xff score=0.31", so each test controls what the model returns.
"""

JPEG = b"\xff\xd8\xff"


def photo(instruction: str) -> bytes:
    return JPEG + b" " + instruction.encode()


class FakeVerifier:
    model_version = "fake-siamese-1"

    def __init__(self):
        self.calls = []

    def similarity(self, image: bytes, gtin: str):
        self.calls.append(gtin)
        instruction = image[len(JPEG):].decode().strip()
        if instruction == "no-reference":
            return None
        if instruction == "crash":
            raise RuntimeError("model exploded")
        return float(instruction.removeprefix("score="))


def load():
    return FakeVerifier()
