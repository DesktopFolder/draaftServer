from typing import Callable
from typing_extensions import override

class Datapack:
    def __init__(self):
        pass

    def onload(self, user: str) -> str:
        return ""

    def ontick(self, user: str) -> str:
        return ""

    # no players for this for now
    def custom_file(self) -> dict[str, str]:
        return {}

    def features(self) -> list[str]:
        return list()

    def description(self) -> str:
        return "error: bad description call"


class FeatureGranter(Datapack):
    def __init__(self, feature: str | list[str]):
        if isinstance(feature, str):
            self.features_ = [feature]
        else:
            self.features_ = feature

    @override
    def features(self) -> list[str]:
        return self.features_


class CustomGranter(Datapack):
    def __init__(self, onload: str | None = None, ontick: str | None = None):
        self.onload_ = onload
        self.ontick_ = ontick

    @override
    def onload(self, user: str) -> str:
        return (self.onload_ or "").format(USERNAME=user)

    @override
    def ontick(self, user: str) -> str:
        return (self.ontick_ or "").format(USERNAME=user)


class LambdaGranter(Datapack):
    def __init__(self, onload: Callable[[str], str] | None = None, ontick: Callable[[str], str] | None = None):
        self.onload_ = onload
        self.ontick_ = ontick

    @override
    def onload(self, user: str) -> str:
        if self.onload_ is not None:
            return self.onload_(user)
        return ""

    @override
    def ontick(self, user: str) -> str:
        if self.ontick_ is not None:
            return self.ontick_(user)
        return ""


class FileGranter(Datapack):
    def __init__(self, file_granter: dict[str, str]):
        self.file_granter = file_granter

    @override
    def custom_file(self) -> dict[str, str]:
        return self.file_granter
