from dataclasses import dataclass


@dataclass
class UpdateProjectDTO:
    user_email: str
    uuid: str
    brain_on: str = False

    def dict(self):
        return {key: value for key, value in self.__dict__.items() if value is not None}


@dataclass
class FeatureVersionDTO:
    uuuid = str
    setup = dict

    def dict(self):
        return {key: value for key, value in self.__dict__.items() if value is not None}
