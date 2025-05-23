from enum import Enum, auto

class IssueStates(Enum):
    waiting_for_title = auto()
    waiting_for_description = auto()
    waiting_for_attachment = auto()
    waiting_for_comment = auto()

class RegistrationStates(Enum):
    waiting_for_contact = auto()
