import torch
from torchvision.models import mobilenet_v3_small, MobileNet_V3_Small_Weights

from augment import DEFECTS, PACKAGE, ROOT, augment, dataset, preprocess  # noqa: F401


class Network(torch.nn.Module):
    def __init__(self, pretrained=False):
        super().__init__()
        base = mobilenet_v3_small(
            weights=MobileNet_V3_Small_Weights.IMAGENET1K_V1 if pretrained else None
        )
        self.features = base.features
        self.pool = torch.nn.AdaptiveAvgPool2d(1)
        self.head = torch.nn.Linear(576, 128)

    def backbone(self, x):
        return self.pool(self.features(x)).flatten(1)

    def forward(self, x):
        return torch.nn.functional.normalize(self.head(self.backbone(x)), dim=1)


def load_model(checkpoint):
    obj = torch.load(checkpoint, map_location="cpu", weights_only=True)
    model = Network()
    model.load_state_dict(obj["state"])
    model.eval()
    return model
